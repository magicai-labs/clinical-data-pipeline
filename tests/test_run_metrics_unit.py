from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from build_run_metrics import metrics_storage_path  # noqa: E402
from run_metrics_lib import snapshot_history_created  # noqa: E402


def _run(tmp_path: Path, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    output = tmp_path / "run_metrics.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_run_metrics.py",
            "--mode",
            "incremental",
            "--workflow-conclusion",
            "success",
            "--started-at",
            "2026-07-12T00:00:00Z",
            "--finished-at",
            "2026-07-12T00:01:00Z",
            "--output",
            str(output),
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_non_shard_summary_uses_common_metric_schema(tmp_path: Path):
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "n_cids": 4,
                "n_cids_total": 6,
                "n_new_rows": 2,
                "n_changed_rows": 3,
                "n_skipped_unchanged_rows": 5,
                "n_error_rows": 1,
            }
        ),
        encoding="utf-8",
    )
    result, metrics = _run(tmp_path, "--summary", str(summary))
    assert result.returncode == 0, result.stderr
    assert metrics["n_shards"] == 1
    assert metrics["n_cids_processed"] == 4
    assert metrics["n_rows_scanned"] == 10
    assert metrics["n_delta_rows"] == 5


def test_checksums_and_unchanged_run_are_recorded(tmp_path: Path):
    summary = tmp_path / "summary.json"
    baseline = tmp_path / "baseline.json"
    state = tmp_path / "state.json"
    latest = tmp_path / "trials.json"
    changed = tmp_path / "changed.txt"
    summary.write_text(
        json.dumps({"n_new_rows": 0, "n_changed_rows": 0, "n_skipped_unchanged_rows": 7}),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps({"latest_checksum": "before", "latest_snapshot": "same"}), encoding="utf-8"
    )
    state.write_text(
        json.dumps(
            {
                "latest_checksum": "after",
                "latest_snapshot": "same",
                "latest_row_count": 7,
                "history_count": 3,
                "last_pruned_count": 0,
                "changed_assets": [],
            }
        ),
        encoding="utf-8",
    )
    latest.write_text("[]\n", encoding="utf-8")
    changed.write_text("false\n", encoding="utf-8")
    result, metrics = _run(
        tmp_path,
        "--summary",
        str(summary),
        "--baseline-state",
        str(baseline),
        "--result-state",
        str(state),
        "--latest-file",
        str(latest),
        "--changed-flag",
        str(changed),
    )
    assert result.returncode == 0, result.stderr
    assert metrics["baseline_checksum"] == "before"
    assert metrics["result_checksum"] == "after"
    assert metrics["dataset_changed"] is False
    assert metrics["history_created"] is False
    assert metrics["latest_file_bytes"] == 3


def test_manifest_reports_total_uncompressed_shard_bytes(tmp_path: Path):
    manifest = tmp_path / "trials" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps({"shards": [{"path": "shard-000.json", "bytes": 11}, {"path": "shard-001.json", "bytes": 17}]}),
        encoding="utf-8",
    )
    result, metrics = _run(tmp_path, "--latest-file", str(manifest))
    assert result.returncode == 0, result.stderr
    assert metrics["latest_file_bytes"] == 28


def test_failure_with_missing_inputs_still_writes_metrics(tmp_path: Path):
    output = tmp_path / "failed.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_run_metrics.py",
            "--mode",
            "full",
            "--workflow-conclusion",
            "failure",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    metrics = json.loads(output.read_text(encoding="utf-8"))
    assert metrics["workflow_conclusion"] == "failure"
    assert metrics["n_new_rows"] is None
    assert metrics["warnings"]


def test_metrics_storage_path_format():
    assert metrics_storage_path("incremental", "123456789", "1", "2026-07-12T03:04:05Z") == Path(
        "runs/2026/07/incremental_123456789_1.json"
    )


def _state(snapshot: str, count: int = 3) -> dict:
    return {
        "latest_snapshot": snapshot,
        "history_counts": {"trials": count},
        "assets": {"trials": {"latest_snapshot": snapshot}},
    }


def test_history_created_when_asset_snapshot_changes_but_count_is_same():
    assert snapshot_history_created(_state("old", 3), _state("new", 3), True) is True


def test_history_not_created_when_asset_snapshot_and_count_are_same():
    assert snapshot_history_created(_state("same", 3), _state("same", 3), False) is False


def test_history_created_when_snapshot_and_pruning_keep_count_flat():
    baseline = _state("trials_20260701.json", 5)
    result = _state("trials_20260712.json", 5)
    result["last_pruned_count"] = 1
    assert snapshot_history_created(baseline, result, True) is True


def test_history_created_for_legacy_top_level_snapshot_change():
    baseline = {"latest_snapshot": "old", "history_counts": {"trials": 2}}
    result = {"latest_snapshot": "new", "history_counts": {"trials": 2}}
    assert snapshot_history_created(baseline, result, True) is True


def test_history_created_on_first_run_without_baseline():
    assert snapshot_history_created({}, _state("first", 1), True) is True


def _write_summary(path: Path, **overrides: int) -> None:
    values = {
        "n_cids": 2,
        "n_cids_total": 10,
        "n_new_rows": 1,
        "n_changed_rows": 2,
        "n_skipped_unchanged_rows": 3,
        "n_error_rows": 0,
    }
    values.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values), encoding="utf-8")


def test_final_summary_takes_priority_over_shard_fallback(tmp_path: Path):
    final = tmp_path / "final.json"
    shard = tmp_path / "shards" / "s1" / "summary.json"
    _write_summary(final, n_new_rows=20)
    _write_summary(shard, n_new_rows=99)
    result, metrics = _run(tmp_path, "--summary", str(final), "--shard-summary-glob", str(shard))
    assert result.returncode == 0, result.stderr
    assert metrics["n_new_rows"] == 20
    assert not any("partial run" in warning for warning in metrics["warnings"])


def test_missing_final_summary_aggregates_completed_shards(tmp_path: Path):
    shard1 = tmp_path / "shards" / "s1" / "summary.json"
    shard2 = tmp_path / "shards" / "s2" / "summary.json"
    _write_summary(shard1, n_cids=2, n_cids_total=10, n_new_rows=1)
    _write_summary(
        shard2,
        n_cids=3,
        n_cids_total=12,
        n_new_rows=4,
        n_changed_rows=1,
        n_skipped_unchanged_rows=2,
    )
    result, metrics = _run(
        tmp_path,
        "--summary",
        str(tmp_path / "missing.json"),
        "--shard-summary-glob",
        str(tmp_path / "shards" / "s*" / "summary.json"),
    )
    assert result.returncode == 0, result.stderr
    assert metrics["n_shards"] == 2
    assert metrics["n_cids_processed"] == 5
    assert metrics["n_cids_total"] == 12
    assert metrics["n_new_rows"] == 5
    assert metrics["n_delta_rows"] == 8
    assert metrics["n_rows_scanned"] == 13
    assert any("2 completed shard" in warning for warning in metrics["warnings"])


def test_partial_and_invalid_shard_summaries_keep_valid_statistics(tmp_path: Path):
    valid = tmp_path / "shards" / "s1" / "summary.json"
    invalid = tmp_path / "shards" / "s2" / "summary.json"
    _write_summary(valid, n_new_rows=7)
    invalid.parent.mkdir(parents=True)
    invalid.write_text("{broken", encoding="utf-8")
    result, metrics = _run(
        tmp_path,
        "--shard-summary-glob",
        str(tmp_path / "shards" / "s*" / "summary.json"),
    )
    assert result.returncode == 0, result.stderr
    assert metrics["n_shards"] == 1
    assert metrics["n_new_rows"] == 7
    assert any("invalid shard summary" in warning for warning in metrics["warnings"])
    assert any("partial run" in warning for warning in metrics["warnings"])


def test_missing_final_and_shard_summaries_leave_counters_null(tmp_path: Path):
    result, metrics = _run(
        tmp_path,
        "--summary",
        str(tmp_path / "missing.json"),
        "--shard-summary-glob",
        str(tmp_path / "shards" / "s*" / "summary.json"),
    )
    assert result.returncode == 0, result.stderr
    assert metrics["n_shards"] is None
    assert metrics["n_new_rows"] is None
    assert any("no valid completed shard" in warning for warning in metrics["warnings"])
