from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/push_git_commit_with_retry.py").resolve()


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _configure(repo: Path) -> None:
    _git("config", "user.name", "Test User", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)


def test_push_rebases_stale_snapshot_commit_without_force(tmp_path: Path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    runner = tmp_path / "runner"
    concurrent = tmp_path / "concurrent"
    _git("init", "--bare", str(remote))
    _git("init", "-b", "main", str(seed))
    _configure(seed)
    (seed / "base.txt").write_text("base\n", encoding="utf-8")
    _git("add", "base.txt", cwd=seed)
    _git("commit", "-m", "base", cwd=seed)
    _git("remote", "add", "origin", str(remote), cwd=seed)
    _git("push", "-u", "origin", "main", cwd=seed)

    _git("clone", "--branch", "main", str(remote), str(runner))
    _git("clone", "--branch", "main", str(remote), str(concurrent))
    _configure(runner)
    _configure(concurrent)

    (concurrent / "code.txt").write_text("new code\n", encoding="utf-8")
    _git("add", "code.txt", cwd=concurrent)
    _git("commit", "-m", "advance main", cwd=concurrent)
    _git("push", "origin", "main", cwd=concurrent)

    (runner / "snapshot.json").write_text('{"rows": 1}\n', encoding="utf-8")
    _git("add", "snapshot.json", cwd=runner)
    _git("commit", "-m", "snapshot", cwd=runner)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--branch", "main", "--retries", "2"],
        cwd=runner,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    tree = _git("--git-dir", str(remote), "ls-tree", "-r", "--name-only", "main").stdout
    assert tree.splitlines() == ["base.txt", "code.txt", "snapshot.json"]
    messages = _git("--git-dir", str(remote), "log", "--format=%s", "main").stdout
    assert messages.splitlines()[:2] == ["snapshot", "advance main"]
