from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/persist_run_metrics.py").resolve()


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _persist(source: Path, metrics_file: Path, mode: str, run_id: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--metrics-file",
            str(metrics_file),
            "--mode",
            mode,
            "--run-id",
            run_id,
            "--run-attempt",
            "1",
            "--finished-at",
            "2026-07-12T03:04:05Z",
        ],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_persist_metrics_creates_and_appends_to_orphan_branch(tmp_path: Path):
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    _git("init", "--bare", str(remote))
    _git("init", str(source))
    _git("remote", "add", "origin", str(remote), cwd=source)

    full_metrics = tmp_path / "full.json"
    incremental_metrics = tmp_path / "incremental.json"
    full_metrics.write_text(json.dumps({"mode": "full"}) + "\n", encoding="utf-8")
    incremental_metrics.write_text(json.dumps({"mode": "incremental"}) + "\n", encoding="utf-8")

    _persist(source, full_metrics, "full", "100")
    first_path = "runs/2026/07/full_100_1.json"
    first_content = _git("--git-dir", str(remote), "show", f"metrics:{first_path}").stdout
    assert json.loads(first_content) == {"mode": "full"}

    _persist(source, incremental_metrics, "incremental", "101")
    second_path = "runs/2026/07/incremental_101_1.json"
    files = _git(
        "--git-dir", str(remote), "ls-tree", "-r", "--name-only", "metrics"
    ).stdout.splitlines()
    assert files == ["README.md", first_path, second_path]
    assert json.loads(_git("--git-dir", str(remote), "show", f"metrics:{first_path}").stdout) == {
        "mode": "full"
    }
    assert json.loads(_git("--git-dir", str(remote), "show", f"metrics:{second_path}").stdout) == {
        "mode": "incremental"
    }
