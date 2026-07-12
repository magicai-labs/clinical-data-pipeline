#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import time


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def is_non_retryable_push_error(stderr: str) -> bool:
    normalized = stderr.lower()
    return any(
        marker in normalized
        for marker in (
            "gh001: large files detected",
            "exceeds github's file size limit",
            "pre-receive hook declined",
            "permission denied",
            "authentication failed",
            "repository not found",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebase the current commit onto a remote branch and push with bounded retries."
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if args.retries < 1:
        parser.error("--retries must be at least 1")

    for attempt in range(1, args.retries + 1):
        print(f"[push] attempt {attempt}/{args.retries}: fetch {args.remote}/{args.branch}")
        _git("fetch", args.remote, args.branch)
        remote_ref = f"{args.remote}/{args.branch}"
        rebase = _git("rebase", remote_ref, check=False)
        if rebase.returncode != 0:
            print("::error::Could not rebase the snapshot commit onto the latest remote branch.")
            if rebase.stdout.strip():
                print(rebase.stdout.strip())
            if rebase.stderr.strip():
                print(rebase.stderr.strip())
            print("::error::Resolve the snapshot conflict manually; no force push was attempted.")
            return 1

        push = _git("push", args.remote, f"HEAD:{args.branch}", check=False)
        if push.returncode == 0:
            if push.stdout.strip():
                print(push.stdout.strip())
            if push.stderr.strip():
                print(push.stderr.strip())
            return 0

        print(
            f"::warning::Push attempt {attempt}/{args.retries} was rejected; "
            "the remote branch may have advanced again."
        )
        if push.stderr.strip():
            print(push.stderr.strip())
        if is_non_retryable_push_error(push.stderr):
            print("::error::Push was rejected permanently; retrying cannot resolve this error.")
            return 1
        if attempt < args.retries:
            time.sleep(attempt)

    print(f"::error::Failed to push after {args.retries} attempts; no force push was attempted.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
