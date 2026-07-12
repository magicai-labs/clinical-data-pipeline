from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_merge_trials_incremental_unit(tmp_path: Path):
    base_rows = [
        {
            "cid": 1,
            "collection": "ClinicalTrials.gov",
            "collection_code": "clinicaltrials",
            "id": "NCT1",
            "status": "Recruiting",
        },
        {
            "cid": 2,
            "collection": "ClinicalTrials.gov",
            "collection_code": "clinicaltrials",
            "id": "NCT2",
            "status": "Completed",
        },
    ]
    delta_rows = [
        {
            "cid": 2,
            "collection": "ClinicalTrials.gov",
            "collection_code": "clinicaltrials",
            "id": "NCT2",
            "status": "Terminated",
        },
        {
            "cid": 3,
            "collection": "ClinicalTrials.gov",
            "collection_code": "clinicaltrials",
            "id": "NCT3",
            "status": "Recruiting",
        },
    ]

    base_json = tmp_path / "base.json"
    delta_json = tmp_path / "delta.json"
    out_dir = tmp_path / "out"

    base_json.write_text(json.dumps(base_rows, ensure_ascii=False), encoding="utf-8")
    delta_json.write_text(json.dumps(delta_rows, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/merge_trials_incremental.py",
            "--base-json",
            str(base_json),
            "--delta-json",
            str(delta_json),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    merged = json.loads((out_dir / "trials.json").read_text(encoding="utf-8"))
    by_key = {(r["cid"], r["id"]): r for r in merged}

    assert len(merged) == 3
    assert by_key[(2, "NCT2")]["status"] == "Terminated"
    assert by_key[(3, "NCT3")]["status"] == "Recruiting"

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_base_rows"] == 2
    assert summary["n_delta_rows"] == 2
    assert summary["n_rows"] == 3
    assert summary["n_cids"] == 3
    assert summary["n_compounds"] == 3

    compounds = json.loads((out_dir / "compounds.json").read_text(encoding="utf-8"))
    compact = json.loads((out_dir / "trials_compact.json").read_text(encoding="utf-8"))
    assert len(compounds) == 3
    assert len(compact) == 3

    # Keep large snapshot files below GitHub's limit by matching the full exporter's
    # one-row-per-line representation instead of expanding every field with indent=2.
    assert len((out_dir / "trials.json").read_text(encoding="utf-8").splitlines()) == 5
    assert len((out_dir / "trials_compact.json").read_text(encoding="utf-8").splitlines()) == 5
