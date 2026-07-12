# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Magic AI Research Association

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/update_pubchem_trials_history.py", *args], capture_output=True, text=True)


def test_update_pubchem_trials_history_unit(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    trials = src / "trials.json"
    trials.write_text('[{"id":"NCT1"}]\n', encoding="utf-8")

    state = tmp_path / "snapshots" / "collection_state.json"
    latest = tmp_path / "snapshots" / "latest" / "trials.json"
    history = tmp_path / "snapshots" / "history"
    flag = tmp_path / "changed.txt"

    r1 = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T00:00:00Z",
            "--changed-flag-path",
            str(flag),
        ]
    )
    assert r1.returncode == 0, r1.stderr
    assert "changed: true" in r1.stdout
    assert latest.exists()
    assert len(list(history.glob("trials_[0-9]*.json"))) == 1
    assert flag.read_text(encoding="utf-8").strip() == "true"

    r2 = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T01:00:00Z",
            "--changed-flag-path",
            str(flag),
        ]
    )
    assert r2.returncode == 0, r2.stderr
    assert "changed: false" in r2.stdout
    assert len(list(history.glob("trials_[0-9]*.json"))) == 2
    assert flag.read_text(encoding="utf-8").strip() == "false"

    state_obj = json.loads(state.read_text(encoding="utf-8"))
    assert state_obj["source"] == "pubchem"
    assert state_obj["latest_row_count"] == 1
    assert state_obj["history_count"] == 2


def test_update_pubchem_trials_history_snapshot_on_change(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    trials = src / "trials.json"
    trials.write_text('[{"id":"NCT1"}]\n', encoding="utf-8")

    state = tmp_path / "snapshots" / "collection_state.json"
    latest = tmp_path / "snapshots" / "latest" / "trials.json"
    history = tmp_path / "snapshots" / "history"

    r1 = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T00:00:00Z",
            "--snapshot-on-change",
        ]
    )
    assert r1.returncode == 0, r1.stderr
    assert len(list(history.glob("trials_[0-9]*.json"))) == 1

    r2 = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T01:00:00Z",
            "--snapshot-on-change",
        ]
    )
    assert r2.returncode == 0, r2.stderr
    assert len(list(history.glob("trials_[0-9]*.json"))) == 1

    trials.write_text('[{"id":"NCT1"},{"id":"NCT2"}]\n', encoding="utf-8")

    r3 = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T02:00:00Z",
            "--snapshot-on-change",
        ]
    )
    assert r3.returncode == 0, r3.stderr
    assert len(list(history.glob("trials_[0-9]*.json"))) == 2


def test_update_pubchem_trials_history_retention_prunes_old(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    trials = src / "trials.json"
    trials.write_text('[{"id":"NCT1"}]\n', encoding="utf-8")

    state = tmp_path / "snapshots" / "collection_state.json"
    latest = tmp_path / "snapshots" / "latest" / "trials.json"
    history = tmp_path / "snapshots" / "history"
    history.mkdir(parents=True, exist_ok=True)

    old_snapshot = history / "trials_20240101T000000Z.json"
    old_snapshot.write_text("[]\n", encoding="utf-8")

    r = _run(
        [
            "--trials-file",
            str(trials),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-23T00:00:00Z",
            "--retention-days",
            "365",
        ]
    )
    assert r.returncode == 0, r.stderr
    assert not old_snapshot.exists()
    assert "pruned_snapshots: 1" in r.stdout

    state_obj = json.loads(state.read_text(encoding="utf-8"))
    assert state_obj["last_pruned_count"] == 1


def test_update_pubchem_trials_history_with_aux_assets_unit(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    trials = src / "trials.json"
    compounds = src / "compounds.json"
    compact = src / "trials_compact.json"

    trials.write_text('[{"cid":1,"id":"NCT1"}]\n', encoding="utf-8")
    compounds.write_text('[{"cid":1,"smiles":"C"}]\n', encoding="utf-8")
    compact.write_text('[{"cid":1,"id":"NCT1"}]\n', encoding="utf-8")

    state = tmp_path / "snapshots" / "collection_state.json"
    latest_trials = tmp_path / "snapshots" / "latest" / "trials.json"
    latest_compounds = tmp_path / "snapshots" / "latest" / "compounds.json"
    latest_compact = tmp_path / "snapshots" / "latest" / "trials_compact.json"
    history = tmp_path / "snapshots" / "history"
    flag = tmp_path / "changed.txt"

    r1 = _run(
        [
            "--trials-file",
            str(trials),
            "--compounds-file",
            str(compounds),
            "--trials-compact-file",
            str(compact),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest_trials),
            "--latest-compounds-file",
            str(latest_compounds),
            "--latest-trials-compact-file",
            str(latest_compact),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T00:00:00Z",
            "--changed-flag-path",
            str(flag),
            "--snapshot-on-change",
        ]
    )
    assert r1.returncode == 0, r1.stderr
    assert "changed: true" in r1.stdout
    assert flag.read_text(encoding="utf-8").strip() == "true"
    assert latest_trials.exists()
    assert latest_compounds.exists()
    assert latest_compact.exists()
    assert len(list(history.glob("trials_[0-9]*.json"))) == 1
    assert len(list(history.glob("compounds_*.json"))) == 1
    assert len(list(history.glob("trials_compact_*.json"))) == 1

    compounds.write_text('[{"cid":1,"smiles":"CC"}]\n', encoding="utf-8")

    r2 = _run(
        [
            "--trials-file",
            str(trials),
            "--compounds-file",
            str(compounds),
            "--trials-compact-file",
            str(compact),
            "--state-file",
            str(state),
            "--latest-file",
            str(latest_trials),
            "--latest-compounds-file",
            str(latest_compounds),
            "--latest-trials-compact-file",
            str(latest_compact),
            "--history-dir",
            str(history),
            "--timestamp",
            "2026-02-10T01:00:00Z",
            "--changed-flag-path",
            str(flag),
            "--snapshot-on-change",
        ]
    )
    assert r2.returncode == 0, r2.stderr
    assert "changed: true" in r2.stdout
    assert "changed_assets: compounds" in r2.stdout
    assert flag.read_text(encoding="utf-8").strip() == "true"
    assert len(list(history.glob("trials_[0-9]*.json"))) == 1
    assert len(list(history.glob("compounds_*.json"))) == 2
    assert len(list(history.glob("trials_compact_*.json"))) == 1

    state_obj = json.loads(state.read_text(encoding="utf-8"))
    assert state_obj["schema_version"] == 2
    assert state_obj["history_counts"]["compounds"] == 2
    assert state_obj["history_counts"]["trials"] == 1
