#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COUNTERS = (
    "n_shards",
    "n_cids_total",
    "n_cids_processed",
    "n_rows_scanned",
    "n_delta_rows",
    "n_new_rows",
    "n_changed_rows",
    "n_skipped_unchanged_rows",
    "n_error_rows",
)


def _read_json(path: Path | None, label: str, warnings: list[str]) -> dict[str, Any]:
    if path is None or not path.exists():
        warnings.append(f"missing {label}: {path or 'not specified'}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"invalid {label}: {path}: {exc}")
        return {}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def metrics_storage_path(mode: str, run_id: str, run_attempt: str, finished_at: str) -> Path:
    timestamp = _parse_time(finished_at)
    if timestamp is None:
        raise ValueError("finished_at must be an ISO 8601 timestamp")
    return (
        Path("runs") / f"{timestamp:%Y}" / f"{timestamp:%m}" / f"{mode}_{run_id}_{run_attempt}.json"
    )


def build_metrics(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    summary = _read_json(args.summary, "summary", warnings)
    baseline = _read_json(args.baseline_state, "baseline state", warnings)
    result = _read_json(args.result_state, "result state", warnings)

    finished_dt = _parse_time(args.finished_at) or datetime.now(timezone.utc)
    finished_at = finished_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    started_dt = _parse_time(args.started_at)
    if started_dt is None:
        warnings.append("missing or invalid started_at")
    elapsed = round((finished_dt - started_dt).total_seconds(), 3) if started_dt else None

    changed: bool | None = None
    if args.changed_flag and args.changed_flag.exists():
        changed = args.changed_flag.read_text(encoding="utf-8").strip().lower() == "true"
    elif result:
        warnings.append(f"missing changed flag: {args.changed_flag or 'not specified'}")

    latest_bytes: int | None = None
    if args.latest_file and args.latest_file.exists():
        latest_bytes = args.latest_file.stat().st_size
    else:
        warnings.append(f"missing latest trials file: {args.latest_file or 'not specified'}")

    result_snapshot = result.get("latest_snapshot")
    baseline_snapshot = baseline.get("latest_snapshot")
    baseline_counts = baseline.get("history_counts")
    result_counts = result.get("history_counts")
    if isinstance(baseline_counts, dict) and isinstance(result_counts, dict):
        history_created = any(
            isinstance(count, int) and count > int(baseline_counts.get(name, 0))
            for name, count in result_counts.items()
        )
    elif result and baseline:
        history_created = result_snapshot != baseline_snapshot
    elif result and changed is True:
        history_created = bool(result_snapshot)
    else:
        history_created = None
    params = {
        name: os.environ.get(name.upper(), "")
        for name in (
            "hnid",
            "extra_hnids",
            "limit_cids",
            "limit_per_collection",
            "shard_size",
            "skip_images",
            "retention_days",
        )
    }
    metrics: dict[str, Any] = {
        "schema_version": 1,
        "repository": args.repository,
        "workflow_name": args.workflow_name,
        "mode": args.mode,
        "event_name": args.event_name,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "run_url": args.run_url,
        "ref_name": args.ref_name,
        "code_sha": args.code_sha,
        "started_at": started_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if started_dt
        else "",
        "finished_at": finished_at,
        "elapsed_sec": elapsed,
        "workflow_conclusion": args.workflow_conclusion,
        "parameters": params,
    }
    for key in COUNTERS:
        metrics[key] = summary.get(key)
    # Backward-compatible non-shard summaries already expose these source fields.
    if metrics["n_cids_processed"] is None:
        metrics["n_cids_processed"] = summary.get("n_cids")
    if metrics["n_shards"] is None and summary:
        metrics["n_shards"] = 1
    new, changed_rows, skipped = (
        summary.get(k) for k in ("n_new_rows", "n_changed_rows", "n_skipped_unchanged_rows")
    )
    if metrics["n_rows_scanned"] is None and all(
        isinstance(v, int) for v in (new, changed_rows, skipped)
    ):
        metrics["n_rows_scanned"] = new + changed_rows + skipped
    if metrics["n_delta_rows"] is None and all(isinstance(v, int) for v in (new, changed_rows)):
        metrics["n_delta_rows"] = new + changed_rows
    metrics.update(
        {
            "baseline_checksum": baseline.get("latest_checksum"),
            "result_checksum": result.get("latest_checksum"),
            "latest_row_count": result.get("latest_row_count"),
            "latest_file_bytes": latest_bytes,
            "dataset_changed": changed,
            "history_created": history_created,
            "history_count": result.get("history_count"),
            "pruned_snapshot_count": result.get("last_pruned_count"),
            "changed_assets": result.get("changed_assets", []),
            "warnings": [*summary.get("warnings", []), *warnings],
        }
    )
    return metrics


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=("full", "incremental"))
    p.add_argument("--summary", type=Path)
    p.add_argument("--baseline-state", type=Path)
    p.add_argument("--result-state", type=Path)
    p.add_argument("--latest-file", type=Path)
    p.add_argument("--changed-flag", type=Path)
    p.add_argument("--started-at")
    p.add_argument("--finished-at")
    p.add_argument(
        "--workflow-conclusion", required=True, choices=("success", "failure", "cancelled")
    )
    p.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--workflow-name", default=os.environ.get("GITHUB_WORKFLOW", ""))
    p.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    p.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    p.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    p.add_argument("--run-url", default="")
    p.add_argument("--ref-name", default=os.environ.get("GITHUB_REF_NAME", ""))
    p.add_argument("--code-sha", default=os.environ.get("GITHUB_SHA", ""))
    p.add_argument("--output", type=Path, default=Path("run_metrics.json"))
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_metrics(args), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
