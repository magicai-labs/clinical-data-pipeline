from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_merge_pubchem_trials_shards_unit(tmp_path: Path):
    shard1 = tmp_path / "shard1"
    shard2 = tmp_path / "shard2"
    shard1.mkdir()
    shard2.mkdir()

    row_a = {
        "cid": 11,
        "collection": "ClinicalTrials.gov",
        "id": "NCT00000011",
        "title": "Trial 11",
        "date": "2020-01-01",
    }
    row_b = {
        "cid": 12,
        "collection": "ClinicalTrials.gov",
        "id": "NCT00000012",
        "title": "Trial 12",
        "date": "2020-01-02",
    }

    (shard1 / "trials.jsonl").write_text(
        json.dumps(row_a, ensure_ascii=False)
        + "\n"
        + json.dumps(row_b, ensure_ascii=False)
        + "\n"
        + json.dumps({"cid": 13, "error": "server busy"})
        + "\n",
        encoding="utf-8",
    )
    # Duplicate row_b across shards to validate dedupe.
    (shard2 / "trials.jsonl").write_text(
        json.dumps(row_b, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (shard1 / "summary.json").write_text(
        json.dumps(
            {
                "n_cids": 2,
                "n_cids_total": 5,
                "n_new_rows": 1,
                "n_changed_rows": 1,
                "n_skipped_unchanged_rows": 3,
                "n_error_rows": 0,
            }
        ),
        encoding="utf-8",
    )
    (shard2 / "summary.json").write_text(
        json.dumps(
            {
                "n_cids": 1,
                "n_cids_total": 5,
                "n_new_rows": 2,
                "n_changed_rows": 0,
                "n_skipped_unchanged_rows": 4,
                "n_error_rows": 1,
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "merged"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/merge_pubchem_trials_shards.py",
            "--shard-dirs",
            f"{shard1},{shard2}",
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    rows = [
        json.loads(x)
        for x in (out_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    assert len(rows) == 2

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_shards"] == 2
    assert summary["n_input_rows"] == 4
    assert summary["n_filtered_nonclinical_rows"] == 1
    assert summary["n_rows"] == 2
    assert summary["n_cids"] == 2
    assert summary["n_compounds"] == 2
    assert summary["n_cids_processed"] == 3
    assert summary["n_cids_total"] == 5
    assert summary["n_new_rows"] == 3
    assert summary["n_changed_rows"] == 1
    assert summary["n_skipped_unchanged_rows"] == 7
    assert summary["n_error_rows"] == 1
    assert summary["n_rows_scanned"] == 11
    assert summary["n_delta_rows"] == 4

    compounds = json.loads((out_dir / "compounds.json").read_text(encoding="utf-8"))
    compact = json.loads((out_dir / "trials_compact.json").read_text(encoding="utf-8"))
    assert len(compounds) == 2
    assert len(compact) == 2


def test_merge_warns_when_shard_summary_is_missing(tmp_path: Path):
    shard = tmp_path / "shard"
    shard.mkdir()
    (shard / "trials.jsonl").write_text('{"cid": 1}\n', encoding="utf-8")
    out_dir = tmp_path / "merged"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/merge_pubchem_trials_shards.py",
            "--shard-dirs",
            str(shard),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["warnings"] == [f"missing shard summary: {shard / 'summary.json'}"]
