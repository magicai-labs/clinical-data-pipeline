#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Magic AI Research Association

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from typing import Dict, List

try:
    from snapshot_shards import write_shards
except ModuleNotFoundError:  # imported as scripts.update_pubchem_trials_history
    from scripts.snapshot_shards import write_shards


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_row_count(path: Path) -> int:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return len(obj)
    return 1


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_snapshot_timestamp(path: Path, prefix: str) -> datetime | None:
    name = path.name
    expected = f"{prefix}_"
    if not (name.startswith(expected) and name.endswith(".json")):
        return None
    token = name[len(expected) : -len(".json")]
    try:
        return datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _prune_old_snapshots(history_dir: Path, now_ts: datetime, retention_days: int, prefixes: List[str]) -> int:
    if retention_days < 0 or not history_dir.exists():
        return 0
    cutoff = now_ts - timedelta(days=retention_days)
    deleted = 0
    for prefix in prefixes:
        for p in history_dir.glob("*.json"):
            snap_ts = _parse_snapshot_timestamp(p, prefix)
            if snap_ts is None:
                continue
            if snap_ts < cutoff:
                p.unlink(missing_ok=True)
                deleted += 1
    for timestamp_dir in history_dir.iterdir():
        if not timestamp_dir.is_dir():
            continue
        try:
            snap_ts = datetime.strptime(timestamp_dir.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if snap_ts < cutoff:
            shutil.rmtree(timestamp_dir)
            deleted += 1
    return deleted


def main() -> int:
    p = argparse.ArgumentParser(prog="update-pubchem-trials-history")
    p.add_argument("--trials-file", required=True, help="Newly collected trials.json path")
    p.add_argument("--compounds-file", default=None, help="Optional newly collected compounds.json path")
    p.add_argument("--trials-compact-file", default=None, help="Optional newly collected trials_compact.json path")
    p.add_argument("--state-file", default="snapshots/clinical_trials/collection_state.json")
    p.add_argument("--latest-file", default="snapshots/clinical_trials/latest/trials.json")
    p.add_argument("--latest-compounds-file", default="snapshots/clinical_trials/latest/compounds.json")
    p.add_argument("--latest-trials-compact-file", default="snapshots/clinical_trials/latest/trials_compact.json")
    p.add_argument("--history-dir", default="snapshots/clinical_trials/history")
    p.add_argument("--shard-count", type=int, default=32, help="Deterministic CID shard count")
    p.add_argument("--timestamp", default=None, help="UTC timestamp override (ISO8601)")
    p.add_argument(
        "--retention-days",
        type=int,
        default=365,
        help="Delete snapshot files older than this many days (default: 365, negative to disable)",
    )
    p.add_argument("--changed-flag-path", default=None, help="Write 'true' or 'false' for workflow")
    p.add_argument(
        "--snapshot-on-change",
        action="store_true",
        help="Save history snapshot only when file content changed (default: snapshot every collection run)",
    )
    args = p.parse_args()

    state_file = Path(args.state_file)
    history_dir = Path(args.history_dir)

    assets: List[Dict[str, object]] = [
        {
            "name": "trials",
            "prefix": "trials",
            "source": Path(args.trials_file),
            "latest": Path(args.latest_file),
        },
        {
            "name": "compounds",
            "prefix": "compounds",
            "source": Path(args.compounds_file) if args.compounds_file else None,
            "latest": Path(args.latest_compounds_file),
        },
        {
            "name": "trials_compact",
            "prefix": "trials_compact",
            "source": Path(args.trials_compact_file) if args.trials_compact_file else None,
            "latest": Path(args.latest_trials_compact_file),
        },
    ]
    all_prefixes = [str(a["prefix"]) for a in assets]

    active_assets: List[Dict[str, object]] = []
    for asset in assets:
        src = asset["source"]
        if src is None:
            continue
        if not isinstance(src, Path) or not src.exists():
            raise FileNotFoundError(f"{asset['name']} file not found: {src}")
        active_assets.append(asset)

    ts = args.timestamp or _now_utc_iso()
    safe_ts = ts.replace(":", "").replace("-", "")
    now_dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)

    prev = _read_state(state_file)
    prev_assets = prev.get("assets") if isinstance(prev.get("assets"), dict) else {}
    changed_assets: List[str] = []
    snapshot_paths: Dict[str, Path] = {}
    state_assets: Dict[str, Dict[str, object]] = dict(prev_assets)

    for asset in active_assets:
        name = str(asset["name"])
        src = asset["source"]
        latest = asset["latest"]
        prefix = str(asset["prefix"])
        assert isinstance(src, Path)
        assert isinstance(latest, Path)
        latest_shard_dir = latest.parent / name

        checksum = _checksum(src)
        rows = _json_row_count(src)

        prev_checksum = None
        prev_asset = prev_assets.get(name)
        if isinstance(prev_asset, dict):
            prev_checksum = prev_asset.get("latest_checksum")
        if name == "trials" and prev_checksum is None:
            prev_checksum = prev.get("latest_checksum")

        changed = checksum != prev_checksum or not (latest_shard_dir / "manifest.json").exists()
        if changed:
            changed_assets.append(name)

        latest.parent.mkdir(parents=True, exist_ok=True)
        latest_manifest = write_shards(
            src, latest_shard_dir, asset=name, generated_at=ts, shard_count=args.shard_count
        )
        # Monolithic latest files eventually exceed GitHub's 100 MiB per-file
        # limit. The manifest and deterministic shards are the canonical copy.
        latest.unlink(missing_ok=True)

        if (not args.snapshot_on_change) or changed:
            history_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = history_dir / f"{prefix}_{safe_ts}.json"
            history_shard_dir = history_dir / safe_ts / name
            write_shards(
                src, history_shard_dir, asset=name, generated_at=ts,
                shard_count=args.shard_count, compress=True,
            )
            snapshot_path = history_shard_dir / "manifest.json"
            snapshot_paths[name] = snapshot_path

        state_assets[name] = {
            "latest_file": str(latest_shard_dir / "manifest.json"),
            "latest_checksum": checksum,
            "latest_row_count": rows,
            "latest_manifest": str(latest_shard_dir / "manifest.json"),
            "shard_count": latest_manifest["shard_count"],
            "latest_snapshot": str(snapshot_paths.get(name)) if name in snapshot_paths else (
                prev_asset.get("latest_snapshot") if isinstance(prev_asset, dict) else ""
            ),
        }

    overall_changed = len(changed_assets) > 0
    deleted_snapshots = _prune_old_snapshots(history_dir, now_dt, args.retention_days, all_prefixes)

    history_counts: Dict[str, int] = {}
    if history_dir.exists():
        for asset in assets:
            prefix = str(asset["prefix"])
            name = str(asset["name"])
            n = 0
            for p in history_dir.glob("*.json"):
                if _parse_snapshot_timestamp(p, prefix) is not None:
                    n += 1
            n += sum(1 for p in history_dir.glob(f"*/{name}/manifest.json"))
            history_counts[name] = n
    else:
        for asset in assets:
            history_counts[str(asset["name"])] = 0

    trials_state = state_assets.get("trials", {})
    latest_file = str(
        trials_state.get(
            "latest_file", Path(args.latest_file).parent / "trials" / "manifest.json"
        )
    )
    latest_checksum = str(trials_state.get("latest_checksum", ""))
    latest_row_count = int(trials_state.get("latest_row_count", 0))
    latest_snapshot = str(trials_state.get("latest_snapshot", prev.get("latest_snapshot", "")))

    state = {
        "schema_version": 3,
        "source": "pubchem",
        "last_collected_at": ts,
        "last_changed_at": ts if overall_changed else prev.get("last_changed_at", ts),
        "latest_file": latest_file,
        "latest_checksum": latest_checksum,
        "latest_row_count": latest_row_count,
        "history_count": history_counts.get("trials", 0),
        "last_pruned_count": deleted_snapshots,
        "latest_snapshot": latest_snapshot,
        "history_counts": history_counts,
        "changed_assets": changed_assets,
        "assets": state_assets,
    }
    _write_state(state_file, state)

    if args.changed_flag_path:
        flag_path = Path(args.changed_flag_path)
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text("true\n" if overall_changed else "false\n", encoding="utf-8")

    print(f"changed: {str(overall_changed).lower()}")
    print(f"latest: {latest_file}")
    print(f"state: {state_file}")
    if "trials" in snapshot_paths:
        print(f"snapshot: {snapshot_paths['trials']}")
    if "compounds" in snapshot_paths:
        print(f"snapshot_compounds: {snapshot_paths['compounds']}")
    if "trials_compact" in snapshot_paths:
        print(f"snapshot_trials_compact: {snapshot_paths['trials_compact']}")
    print(f"changed_assets: {','.join(changed_assets) if changed_assets else '-'}")
    print(f"pruned_snapshots: {deleted_snapshots}")
    print(f"rows: {latest_row_count}")
    print(f"checksum: {latest_checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
