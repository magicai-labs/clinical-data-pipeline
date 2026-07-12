#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from build_run_metrics import metrics_storage_path


def _git(
    *args: str, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=True, capture_output=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics-file", type=Path, required=True)
    p.add_argument("--mode", choices=("full", "incremental"), required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--run-attempt", required=True)
    p.add_argument("--finished-at", required=True)
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default="metrics")
    p.add_argument("--retries", type=int, default=3)
    args = p.parse_args()
    destination = metrics_storage_path(args.mode, args.run_id, args.run_attempt, args.finished_at)
    remote_url = _git("remote", "get-url", args.remote).stdout.strip()
    token = os.environ.get("GITHUB_TOKEN")
    if token and remote_url.startswith("https://github.com/"):
        remote_url = remote_url.replace(
            "https://github.com/", f"https://x-access-token:{token}@github.com/", 1
        )

    for attempt in range(1, args.retries + 1):
        try:
            with tempfile.TemporaryDirectory(prefix="run-metrics-") as tmp:
                work = Path(tmp)
                exists = (
                    _git(
                        "ls-remote", "--exit-code", "--heads", args.remote, args.branch, check=False
                    ).returncode
                    == 0
                )
                if exists:
                    _git(
                        "clone",
                        "--quiet",
                        "--single-branch",
                        "--branch",
                        args.branch,
                        "--depth",
                        "1",
                        remote_url,
                        str(work),
                    )
                else:
                    _git("init", "--quiet", str(work))
                    _git("checkout", "--orphan", args.branch, cwd=work)
                    _git("remote", "add", args.remote, remote_url, cwd=work)
                    (work / "README.md").write_text(
                        "# Workflow run metrics\n\nOne JSON file per GitHub Actions run.\n",
                        encoding="utf-8",
                    )
                target = work / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.metrics_file, target)
                _git("config", "user.name", "github-actions[bot]", cwd=work)
                _git(
                    "config",
                    "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com",
                    cwd=work,
                )
                _git("add", "README.md", str(destination), cwd=work)
                _git(
                    "commit",
                    "-m",
                    f"chore(metrics): record {args.mode} run {args.run_id}/{args.run_attempt}",
                    cwd=work,
                )
                _git("push", args.remote, f"HEAD:{args.branch}", cwd=work)
                print(destination)
                return 0
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip()
            if token:
                detail = detail.replace(token, "***")
            print(
                f"::warning::metrics branch push attempt {attempt}/{args.retries} failed: {detail}"
            )
            if attempt < args.retries:
                time.sleep(attempt)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
