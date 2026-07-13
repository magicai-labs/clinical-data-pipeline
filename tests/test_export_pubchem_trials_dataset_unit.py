from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def test_export_pubchem_trials_dataset_unit(tmp_path: Path):
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()

    pkg = stub_dir / "clinical_data_analyzer"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    pubchem_pkg = pkg / "pubchem"
    pubchem_pkg.mkdir()
    (pubchem_pkg / "__init__.py").write_text(
        "class PubChemClassificationClient:\n"
        "    def get_cids(self, hnid, fmt='TXT'):\n"
        "        return [119]\n\n"
        "class PubChemClient:\n"
        "    def compound_properties(self, cid):\n"
        "        return {'CanonicalSMILES':'C1=CC=CC=C1','InChIKey':'KEY','IUPACName':'benzene'}\n\n"
        "class PubChemWebFallbackClient:\n"
        "    def get_normalized_trials_union(self, cid, collections=('clinicaltrials',), limit_per_collection=200):\n"
        "        rows=[\n"
        "          {'collection':'clinicaltrials','id':'NCT00000001','title':'Trial A','phase':'Phase 2','status':'Completed','date':'2020-01-01','id_url':'https://clinicaltrials.gov/study/NCT00000001'},\n"
        "          {'collection':'clinicaltrials_eu','id':'2006-006023-39','title':'Trial EU','phase':'Phase 2','status':'Completed','date':'2007-09-24','id_url':'https://www.clinicaltrialsregister.eu/ctr-search/search?query=2006-006023-39','eudractnumber':'2006-006023-39'},\n"
        "        ]\n"
        "        keys=sorted({k for r in rows for k in r.keys()})\n"
        "        return rows, keys\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    env = {"PYTHONPATH": str(stub_dir)}

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pubchem_trials_dataset.py",
            "--hnid",
            "3647573",
            "--out-dir",
            str(out_dir),
            "--skip-images",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr

    jsonl_path = out_dir / "trials.jsonl"
    csv_path = out_dir / "trials.csv"
    json_path = out_dir / "trials.json"
    compounds_json_path = out_dir / "compounds.json"
    trials_compact_json_path = out_dir / "trials_compact.json"
    summary_path = out_dir / "summary.json"

    assert jsonl_path.exists()
    assert csv_path.exists()
    assert json_path.exists()
    assert compounds_json_path.exists()
    assert trials_compact_json_path.exists()
    assert summary_path.exists()

    rows = [json.loads(x) for x in jsonl_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 2
    assert rows[0]["cid"] == 119
    assert rows[0]["smiles"] == "C1=CC=CC=C1"

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)
    assert len(csv_rows) == 2
    assert csv_rows[0]["id"] == "NCT00000001"

    json_arr = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(json_arr, list)
    assert len(json_arr) == 2
    compounds_arr = json.loads(compounds_json_path.read_text(encoding="utf-8"))
    assert len(compounds_arr) == 1
    assert compounds_arr[0]["cid"] == 119
    compact_arr = json.loads(trials_compact_json_path.read_text(encoding="utf-8"))
    assert len(compact_arr) == 2
    assert "smiles" not in compact_arr[0]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["n_cids"] == 1
    assert summary["n_rows"] == 2
    assert summary["n_compounds"] == 1


def test_export_pubchem_trials_dataset_shard_options_unit(tmp_path: Path):
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()

    pkg = stub_dir / "clinical_data_analyzer"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    pubchem_pkg = pkg / "pubchem"
    pubchem_pkg.mkdir()
    (pubchem_pkg / "__init__.py").write_text(
        "class PubChemClassificationClient:\n"
        "    def get_cids(self, hnid, fmt='TXT'):\n"
        "        return [11, 12, 13, 14]\n\n"
        "class PubChemClient:\n"
        "    def compound_properties(self, cid):\n"
        "        return {'CanonicalSMILES':'C','InChIKey':'K','IUPACName':'x'}\n\n"
        "class PubChemWebFallbackClient:\n"
        "    def get_normalized_trials_union(self, cid, collections=('clinicaltrials',), limit_per_collection=200):\n"
        "        rows=[{'collection':'clinicaltrials','id':f'NCT{cid}','title':'T','phase':'P2','status':'Completed','date':'2020-01-01','id_url':'u'}]\n"
        "        return rows, sorted(rows[0].keys())\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    env = {"PYTHONPATH": str(stub_dir)}

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pubchem_trials_dataset.py",
            "--hnid",
            "3647573",
            "--out-dir",
            str(out_dir),
            "--skip-images",
            "--cid-offset",
            "1",
            "--cid-count",
            "2",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    cids = [x for x in (out_dir / "cids.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert cids == ["12", "13"]

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_cids_total"] == 4
    assert summary["n_cids"] == 2
    assert summary["cid_offset"] == 1
    assert summary["cid_count"] == 2


def test_export_pubchem_trials_dataset_uses_cids_file_unit(tmp_path: Path):
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()

    pkg = stub_dir / "clinical_data_analyzer"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    pubchem_pkg = pkg / "pubchem"
    pubchem_pkg.mkdir()
    (pubchem_pkg / "__init__.py").write_text(
        "class PubChemClassificationClient:\n"
        "    def get_cids(self, hnid, fmt='TXT'):\n"
        "        raise AssertionError('get_cids should not be called when --cids-file is provided')\n\n"
        "class PubChemClient:\n"
        "    def compound_properties(self, cid):\n"
        "        return {'CanonicalSMILES':'C','InChIKey':'K','IUPACName':'x'}\n\n"
        "class PubChemWebFallbackClient:\n"
        "    def get_normalized_trials_union(self, cid, collections=('clinicaltrials',), limit_per_collection=200):\n"
        "        rows=[{'collection':'clinicaltrials','collection_code':'clinicaltrials','id':f'NCT{cid}','title':'T','phase':'P2','status':'Completed','date':'2020-01-01','id_url':'u'}]\n"
        "        return rows, sorted(rows[0].keys())\n",
        encoding="utf-8",
    )

    cids_file = tmp_path / "cids.txt"
    cids_file.write_text("101\n102\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    env = {"PYTHONPATH": str(stub_dir)}

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pubchem_trials_dataset.py",
            "--hnid",
            "3647573",
            "--out-dir",
            str(out_dir),
            "--skip-images",
            "--cids-file",
            str(cids_file),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    cids = [x for x in (out_dir / "cids.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert cids == ["101", "102"]
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["cids_file"] == str(cids_file)
    assert summary["n_cids_total"] == 2
    assert summary["n_cids"] == 2
    assert summary["n_rows"] == 2


def test_export_omits_no_trial_and_error_placeholders(tmp_path: Path):
    stub_dir = tmp_path / "stubs"
    pkg = stub_dir / "clinical_data_analyzer"
    pubchem_pkg = pkg / "pubchem"
    pubchem_pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pubchem_pkg / "__init__.py").write_text(
        "class PubChemClassificationClient:\n"
        "    def get_cids(self, hnid, fmt='TXT'):\n"
        "        return [101, 102]\n\n"
        "class PubChemClient:\n"
        "    def compound_properties(self, cid):\n"
        "        return {'CanonicalSMILES':'C'}\n\n"
        "class PubChemWebFallbackClient:\n"
        "    def get_normalized_trials_union(self, cid, collections=('clinicaltrials',), limit_per_collection=200):\n"
        "        if cid == 102:\n"
        "            raise RuntimeError('server busy')\n"
        "        return [], []\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pubchem_trials_dataset.py",
            "--hnid",
            "1856916",
            "--out-dir",
            str(out_dir),
            "--skip-images",
        ],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(stub_dir)},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((out_dir / "trials.json").read_text(encoding="utf-8")) == []
    assert json.loads((out_dir / "trials_compact.json").read_text(encoding="utf-8")) == []
    assert (out_dir / "cids.txt").read_text(encoding="utf-8").splitlines() == ["101", "102"]
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_rows"] == 0
    assert summary["n_cids_with_trials"] == 0
    assert summary["n_error_rows"] == 1


def test_export_pubchem_trials_dataset_incremental_skip_unit(tmp_path: Path):
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()

    pkg = stub_dir / "clinical_data_analyzer"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    pubchem_pkg = pkg / "pubchem"
    pubchem_pkg.mkdir()
    (pubchem_pkg / "__init__.py").write_text(
        "class PubChemClassificationClient:\n"
        "    def get_cids(self, hnid, fmt='TXT'):\n"
        "        return [119]\n\n"
        "class PubChemClient:\n"
        "    def compound_properties(self, cid):\n"
        "        return {'CanonicalSMILES':'C1=CC=CC=C1','InChIKey':'KEY','IUPACName':'benzene'}\n\n"
        "class PubChemWebFallbackClient:\n"
        "    def get_normalized_trials_union(self, cid, collections=('clinicaltrials',), limit_per_collection=200):\n"
        "        rows=[\n"
        "          {'collection':'clinicaltrials','collection_code':'clinicaltrials','id':'NCT00000001','title':'Trial A','phase':'Phase 2','status':'Completed','date':'2020-01-01','id_url':'https://clinicaltrials.gov/study/NCT00000001'}\n"
        "        ]\n"
        "        return rows, sorted(rows[0].keys())\n",
        encoding="utf-8",
    )

    base_rows = [
        {
            "collection": "clinicaltrials",
            "collection_code": "clinicaltrials",
            "id": "NCT00000001",
            "title": "Trial A",
            "phase": "Phase 2",
            "status": "Completed",
            "date": "2020-01-01",
            "id_url": "https://clinicaltrials.gov/study/NCT00000001",
            "cid": 119,
            "smiles": "C1=CC=CC=C1",
            "inchikey": "KEY",
            "iupac_name": "benzene",
        }
    ]
    base_json = tmp_path / "base.json"
    base_json.write_text(json.dumps(base_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    env = {"PYTHONPATH": str(stub_dir)}

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_pubchem_trials_dataset.py",
            "--hnid",
            "3647573",
            "--out-dir",
            str(out_dir),
            "--skip-images",
            "--incremental-from",
            str(base_json),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_rows"] == 0
    assert summary["n_new_rows"] == 0
    assert summary["n_changed_rows"] == 0
    assert summary["n_skipped_unchanged_rows"] == 1
