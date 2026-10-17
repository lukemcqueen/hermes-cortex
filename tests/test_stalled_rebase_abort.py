#!/usr/bin/env python3
"""Behavioural test for ops/scripts/lib/git-stalled-rebase.sh (the shipped helper).

The defect being pinned (measured live 2026-10-18): a sync that runs
`git pull --rebase` and hits a conflict leaves the repository STOPPED MID-REBASE,
and a conflicted index refuses every commit and push on the host until someone
cleans it up by hand.

This test builds that exact state in a throwaway repo, PROVES the state is
uncommittable, then calls the SHIPPED helper (sourced from the repo, not a copy
of its logic) and asserts the repository is usable again with every commit
preserved.

Run:  bash tests/run-tests.sh tests/test_stalled_rebase_abort.py
      python3 tests/test_stalled_rebase_abort.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "ops" / "scripts" / "lib" / "git-stalled-rebase.sh"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def git(repo: Path, *args: str, check_rc: bool = True):
    """Run git hermetically: no global/system config, so the host's hooks and
    aliases cannot decide the verdict (its checkout sets core.hooksPath)."""
    full = dict(os.environ)
    full.update(
        {
            "HOME": str(repo.parent),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "probe",
            "GIT_AUTHOR_EMAIL": "probe@example.com",
            "GIT_COMMITTER_NAME": "probe",
            "GIT_COMMITTER_EMAIL": "probe@example.com",
        }
    )
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=full, timeout=60
    )
    if check_rc and done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} rc={done.returncode}\n{done.stderr}")
    return done


def build_conflicted_rebase(root: Path) -> tuple[Path, str]:
    """Return (repo, local_tip) where a `git pull --rebase`-style rebase has
    STOPPED on a conflict and is waiting for a human."""
    repo = root / "conflicted"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()

    # the local commit a sync would be carrying
    (repo / "f.txt").write_text("local\n")
    git(repo, "commit", "-q", "-am", "local work")
    local_tip = git(repo, "rev-parse", "HEAD").stdout.strip()

    # an upstream commit touching the same line -> the rebase conflicts
    git(repo, "checkout", "-q", "-b", "upstream", base)
    (repo / "f.txt").write_text("upstream\n")
    git(repo, "commit", "-q", "-am", "upstream work")
    git(repo, "checkout", "-q", "main")

    done = git(repo, "rebase", "upstream", check_rc=False)
    assert done.returncode != 0, "the probe failed to construct a conflict — nothing is being tested"
    return repo, local_tip


def run_helper(repo: Path) -> subprocess.CompletedProcess:
    """Call the SHIPPED helper for real: source the repo's lib, then invoke it."""
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}" && abort_stalled_rebase'],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "HOME": str(repo.parent)},
    )


def case_conflicted_rebase_is_recovered(root: Path) -> None:
    print("\nCASE 1 — a stopped rebase is aborted and the repo becomes usable")
    repo, local_tip = build_conflicted_rebase(root)
    gd = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())

    # (a) PROBE THE PROBE: the constructed state must really be broken, or the
    #     assertions below would pass on a repo that was never in the bad state.
    check("stopped rebase present before the helper", (gd / "rebase-merge").is_dir())
    check("index carries an unmerged path", "UU" in git(repo, "status", "--porcelain").stdout)
    blocked = git(repo, "commit", "-q", "--allow-empty", "-m", "can I commit?", check_rc=False)
    check(
        "a commit is REFUSED while the rebase is stopped",
        blocked.returncode != 0 and "unmerged" in (blocked.stderr + blocked.stdout).lower(),
        f"rc={blocked.returncode}",
    )

    # (b) the shipped helper
    done = run_helper(repo)

    check("helper rc 0", done.returncode == 0, f"rc={done.returncode} {done.stderr.strip()}")
    check("helper reports the abort", "aborted a stopped rebase" in done.stdout, done.stdout.strip())
    check(
        "no rebase state remains",
        not (gd / "rebase-merge").is_dir() and not (gd / "rebase-apply").is_dir(),
    )
    check("no unmerged path remains", "UU" not in git(repo, "status", "--porcelain").stdout)
    check(
        "the local commit is preserved (HEAD == pre-rebase tip)",
        git(repo, "rev-parse", "HEAD").stdout.strip() == local_tip,
    )
    check(
        "the local commit is still in the log by subject",
        "local work" in git(repo, "log", "--oneline").stdout,
    )
    now_ok = git(repo, "commit", "-q", "--allow-empty", "-m", "after abort", check_rc=False)
    check("a commit now SUCCEEDS", now_ok.returncode == 0, f"rc={now_ok.returncode}")


def case_clean_repo_is_a_noop(root: Path) -> None:
    print("\nCASE 2 — the helper is silent and inert on a repo with no rebase")
    repo = root / "clean"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-q", "-m", "base")
    before = git(repo, "rev-parse", "HEAD").stdout.strip()

    done = run_helper(repo)

    check("helper rc 0", done.returncode == 0, f"rc={done.returncode}")
    check("stdout is EMPTY (the silence contract)", done.stdout == "", repr(done.stdout))
    check("HEAD unchanged", git(repo, "rev-parse", "HEAD").stdout.strip() == before)


def main() -> int:
    if not LIB.is_file():
        print(f"FAIL: the shipped helper is missing: {LIB}")
        return 1
    print(f"helper under test: {LIB}  ({LIB.stat().st_size} bytes)")
    root = Path(
        tempfile.mkdtemp(prefix="stalled-rebase-probe-", dir=os.environ.get("TMPDIR") or None)
    )
    try:
        case_conflicted_rebase_is_recovered(root)
        case_clean_repo_is_a_noop(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{'ALL PASS' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
