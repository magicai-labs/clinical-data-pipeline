from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from build_run_metrics import metrics_storage_path  # noqa: E402


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
