from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

SHARD_COUNTERS = (
    "n_new_rows",
    "n_changed_rows",
    "n_skipped_unchanged_rows",
    "n_error_rows",
)


def aggregate_shard_summary_files(
    summary_paths: Iterable[Path],
) -> tuple[dict[str, int], list[str]]:
    """Aggregate valid completed shard summaries and report unusable inputs."""
    totals = {
        "n_shards": 0,
        "n_cids_processed": 0,
        "n_cids_total": 0,
        **{key: 0 for key in SHARD_COUNTERS},
    }
    warnings: list[str] = []
    for path in summary_paths:
        if not path.exists():
            warnings.append(f"missing shard summary: {path}")
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(summary, dict):
                raise ValueError("top-level JSON value is not an object")
            totals["n_shards"] += 1
            totals["n_cids_processed"] += int(summary.get("n_cids", 0))
            totals["n_cids_total"] = max(
                totals["n_cids_total"], int(summary.get("n_cids_total", 0))
            )
            for key in SHARD_COUNTERS:
                totals[key] += int(summary.get(key, 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            warnings.append(f"invalid shard summary: {path}: {exc}")
    totals["n_rows_scanned"] = (
        totals["n_new_rows"] + totals["n_changed_rows"] + totals["n_skipped_unchanged_rows"]
    )
    totals["n_delta_rows"] = totals["n_new_rows"] + totals["n_changed_rows"]
    return totals, warnings


def snapshot_history_created(
    baseline: dict[str, Any], result: dict[str, Any], dataset_changed: bool | None
) -> bool | None:
    """Detect a new snapshot by path first, even when pruning keeps counts flat."""
    asset_names = ("trials", "compounds", "trials_compact")
    baseline_assets = baseline.get("assets") if isinstance(baseline.get("assets"), dict) else {}
    result_assets = result.get("assets") if isinstance(result.get("assets"), dict) else {}

    result_asset_snapshots = {
        name: asset.get("latest_snapshot")
        for name in asset_names
        if isinstance((asset := result_assets.get(name)), dict) and asset.get("latest_snapshot")
    }
    if result_asset_snapshots and not baseline:
        return True if dataset_changed is True else None
    if result_asset_snapshots and baseline_assets:
        for name, result_snapshot in result_asset_snapshots.items():
            baseline_asset = baseline_assets.get(name)
            baseline_snapshot = (
                baseline_asset.get("latest_snapshot") if isinstance(baseline_asset, dict) else None
            )
            if result_snapshot != baseline_snapshot:
                return True
        return False

    result_snapshot = result.get("latest_snapshot")
    if result_snapshot:
        if not baseline:
            return True if dataset_changed is True else None
        return result_snapshot != baseline.get("latest_snapshot")

    baseline_counts = baseline.get("history_counts")
    result_counts = result.get("history_counts")
    if isinstance(baseline_counts, dict) and isinstance(result_counts, dict):
        return any(
            isinstance(count, int) and count > int(baseline_counts.get(name, 0))
            for name, count in result_counts.items()
        )
    return None
