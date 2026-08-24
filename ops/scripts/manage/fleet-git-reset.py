#!/usr/bin/env python3
"""fleet-git-reset.py — fleet-safe git alignment after a force-push history rewrite.

Purpose: after a history rewrite + force-push on origin/main (e.g. PII commit-
message scrub), every content host must align its local main to the REWRITTEN
origin/main, or its next `git pull --rebase` conflicts forever (pipeline
retries block on rebase-conflict abort). This script performs that alignment
SAFELY and reports exactly what it did.

Safety guards (fail closed):
  * Only operates on ~/hermes-cortex — never an arbitrary repo.
  * Verifies the origin remote URL is the canonical hermes-cortex repo.
  * Requires an explicit mode: --check (dry-run, touches nothing) or --reset.
  * Refuses to reset a DIRTY worktree (uncommitted changes would be lost)
    unless --force is passed deliberately.
  * Refuses if origin/main is unreachable after fetch (no blind resets).
  * Refuses if not on the main branch (only main is aligned).
  * Prints before/after SHAs + a JSON summary line for EXEC_RESULT evidence.

Usage (via bus EXEC — deployed to ~/.hermes-cortex/scripts/):
    python3 fleet-git-reset.py --check            # dry-run report
    python3 fleet-git-reset.py --reset            # align local main to origin/main
    python3 fleet-git-reset.py --reset --force    # allow dirty worktree (deliberate)

Exit codes:
    0 = aligned (or check clean)
    1 = alignment failed (blocker — see stdout/stderr)
    2 = safety guard refused (wrong repo/remote/branch, dirty without --force)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
TARGET_REPO = HOME / "hermes-cortex"
EXPECTED_REMOTE = "https://github.com/lukemcqueen/hermes-cortex.git"


def canonical_remote(url: str) -> str:
    """Normalize a git remote URL to scheme://host/path, stripping credentials.

    Hosts may store the origin URL with an embedded token
    (https://<token>@github.com/lukemcqueen/hermes-cortex.git) — that is still
    the canonical repo, and the guard must not refuse it (kustos, 2026-08-13;
    remote corrected from the pre-rewrite fleet-operator URL 2026-08-24).
    Non-http URLs (ssh, file) are returned unchanged.
    """
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        from urllib.parse import urlparse, urlunparse
        try:
            p = urlparse(url)
            host = p.netloc.rsplit("@", 1)[-1]  # strip userinfo
            return urlunparse((p.scheme, host, p.path, "", "", ""))
        except Exception:
            return url
    return url


def git(args: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          cwd=str(cwd), timeout=timeout)


def main() -> int:
    p = argparse.ArgumentParser(description="Fleet-safe git alignment (post-force-push).")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Dry-run: report divergence, touch nothing")
    mode.add_argument("--reset", action="store_true", help="git fetch origin && git reset --hard origin/main")
    p.add_argument("--force", action="store_true", help="Allow reset with a dirty worktree (deliberate)")
    args = p.parse_args()

    summary = {"mode": "reset" if args.reset else "check", "repo": str(TARGET_REPO),
               "aligned": False, "before": None, "after": None, "origin_main": None,
               "dirty": False, "branch": None, "guard": None}

    # ── Guard 1: repo exists and is a git repo ──────────────────────────
    if not (TARGET_REPO / ".git").exists():
        summary["guard"] = f"not a git repo: {TARGET_REPO}"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 2
    r = git(["rev-parse", "--is-inside-work-tree"], TARGET_REPO)
    if r.returncode != 0:
        summary["guard"] = "rev-parse failed"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 2

    # ── Guard 2: canonical remote (credential-insensitive) ────────────────
    r = git(["remote", "get-url", "origin"], TARGET_REPO)
    remote = r.stdout.strip() if r.returncode == 0 else ""
    if canonical_remote(remote) != EXPECTED_REMOTE:
        summary["guard"] = f"unexpected origin remote: {remote!r}"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 2

    # ── Guard 3: on main branch ─────────────────────────────────────────
    r = git(["branch", "--show-current"], TARGET_REPO)
    branch = r.stdout.strip() if r.returncode == 0 else ""
    summary["branch"] = branch
    if branch != "main":
        summary["guard"] = f"not on main (on {branch!r})"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 2

    # ── Fetch origin (read-only) ────────────────────────────────────────
    r = git(["fetch", "origin", "--quiet"], TARGET_REPO)
    if r.returncode != 0:
        summary["guard"] = f"git fetch origin failed: {r.stderr.strip()[:200]}"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 1

    # ── Read SHAs ───────────────────────────────────────────────────────
    before = git(["rev-parse", "HEAD"], TARGET_REPO).stdout.strip()
    origin_main = git(["rev-parse", "origin/main"], TARGET_REPO)
    if origin_main.returncode != 0:
        summary["guard"] = "origin/main not found after fetch"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 1
    origin_main = origin_main.stdout.strip()
    summary["before"] = before
    summary["origin_main"] = origin_main

    # ── Dirty worktree check (only matters for --reset) ─────────────────
    r = git(["status", "--porcelain"], TARGET_REPO)
    dirty = bool(r.stdout.strip()) if r.returncode == 0 else True
    summary["dirty"] = dirty

    if args.check:
        aligned = before == origin_main
        summary["aligned"] = aligned
        ahead = git(["rev-list", "--count", "origin/main..HEAD"], TARGET_REPO).stdout.strip()
        behind = git(["rev-list", "--count", "HEAD..origin/main"], TARGET_REPO).stdout.strip()
        print(json.dumps(summary))
        print(f"CHECK: local main={before[:12]} origin/main={origin_main[:12]} "
              f"ahead={ahead} behind={behind} dirty={dirty} "
              f"{'ALIGNED' if aligned else 'DIVERGED (reset needed)'}")
        return 0 if aligned else 1

    # ── --reset path ────────────────────────────────────────────────────
    if dirty and not args.force:
        summary["guard"] = "dirty worktree (uncommitted changes would be lost); pass --force to override"
        print(json.dumps(summary)); print(f"REFUSED: {summary['guard']}", file=sys.stderr)
        return 2

    r = git(["reset", "--hard", "origin/main"], TARGET_REPO)
    if r.returncode != 0:
        summary["guard"] = f"git reset --hard origin/main failed: {r.stderr.strip()[:200]}"
        print(json.dumps(summary)); print(f"FAILED: {summary['guard']}", file=sys.stderr)
        return 1

    after = git(["rev-parse", "HEAD"], TARGET_REPO).stdout.strip()
    summary["after"] = after
    summary["aligned"] = after == origin_main
    print(json.dumps(summary))
    print(f"RESET: local main {before[:12]} -> {after[:12]} "
          f"(origin/main={origin_main[:12]}) aligned={summary['aligned']}")
    return 0 if summary["aligned"] else 1


if __name__ == "__main__":
    sys.exit(main())
