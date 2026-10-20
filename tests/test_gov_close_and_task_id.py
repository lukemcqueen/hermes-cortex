#!/usr/bin/env python3
"""Governance close-path and pre-commit task-id regression guards.

Two defects fixed 2026-10-20, both reported from the field (Titus, via Luke):

1. A cycle that changed NOTHING was closed with
   "Review receipt NOT written — range X..X lists no files" plus a warning
   that the push gate would refuse the push. There is no range and there is
   nothing to push, so the warning sent the reader chasing a stale base that does
   not exist. The no-op case is now tagged and reported as information; every
   real bail keeps the warning and the remedy.

2. The pre-commit hook built its task id with `$(cmd || echo fallback)`, which
   captures the command's stdout AND the fallback's when the command prints and
   then exits non-zero. `git rev-parse --abbrev-ref HEAD` in a repo with no
   commits prints "HEAD" and fails, so ids like
   "precommit-repo-HEAD\\nunknown/update" entered the ledger (6,395 rows, 62 ids).

Run: python3 tests/test_gov_close_and_task_id.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"
HOOK = REPO / "ops" / "scripts" / "pre-commit-score"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def load_mcp():
    spec = importlib.util.spec_from_file_location("lg_under_test", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        env={**os.environ, **(env or {})},
    )


def test_no_op_close_is_information_not_a_hazard() -> None:
    m = load_mcp()
    tag = m._RECEIPT_NO_OP

    # The production call site is `receipt_note = _receipt_close_note(receipt_fail)`
    # and _write_review_receipt() returns None whenever it SUCCEEDS — so None and
    # "" are the values this helper actually receives on every clean close, not a
    # hypothetical input. Both must add nothing to the close message.
    check(m._receipt_close_note(None) == "", "a None receipt failure must add no note")
    check(m._receipt_close_note("") == "", "an empty receipt failure must add no note")

    noop = m._receipt_close_note(tag + "HEAD (abc123) is already origin/main — nothing changed")
    check("No review receipt" in noop, "the no-op close must say no receipt was written")
    check("no action needed" in noop, "the no-op close must say no action is needed")
    check("push gate will refuse" not in noop,
          "the no-op close must NOT warn that the push gate will refuse a push "
          "(there is nothing to push)")
    check("Resolve the cause and close again" not in noop,
          "the no-op close must not invite a pointless re-close")
    check(tag not in noop, "the internal no-op tag must not reach the reader")

    fault = m._receipt_close_note("could not resolve HEAD in /srv/checkout (git failed)")
    check("Review receipt NOT written" in fault, "a real bail must still be a warning")
    check("push gate will refuse" in fault,
          "a real bail must still warn that the push gate can refuse the push")
    check("close again BEFORE" in fault, "a real bail must keep its remedy")


def test_first_commit_task_id_has_no_continuation_line() -> None:
    """The exact field case: a repo whose FIRST commit runs the hook.

    Before the fix the branch field held "HEAD\\nunknown" — the command's own
    stdout followed by the fallback — so every such cycle landed under a
    newline-bearing id.
    """
    if not HOOK.exists():
        print(f"SKIP  {HOOK} absent")
        return
    tmp = Path(tempfile.mkdtemp(prefix="taskid-"))
    try:
        repo = tmp / "repo"
        repo.mkdir()
        check(_git(repo, "init", "-q").returncode == 0, "git init failed in the fixture")
        _git(repo, "config", "user.email", "fixture@example.com")
        _git(repo, "config", "user.name", "fixture")
        hooks = repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HOOK, hooks / "pre-commit")
        os.chmod(hooks / "pre-commit", 0o755)
        # Pin the hook path: a host-wide `core.hooksPath` (the deployed hook)
        # otherwise wins and this test silently grades the INSTALLED copy instead
        # of the one in the repo — the first run of this guard did exactly that.
        _git(repo, "config", "core.hooksPath", str(hooks))
        (repo / "file.txt").write_text("x\n")
        _git(repo, "add", "file.txt")

        db = tmp / "scratch-loop-governance.db"
        # The prod ledger must not move: PRE_COMMIT_SCORE_DB is the hook's
        # documented override, and this test proves it is honoured rather than
        # trusting it. Without this, a broken override would let a fixture commit
        # write into the real ledger and the test would still pass.
        prod_db = Path(os.environ.get(
            "PROD_LOOP_GOV_DB", Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"))
        def _ledger_state(path: Path):
            if not path.exists():
                return None
            try:
                con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                n = con.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
                mx = con.execute("SELECT COALESCE(MAX(id), 0) FROM loop_cycles").fetchone()[0]
                con.close()
                return (n, mx)
            except sqlite3.Error:
                return None

        prod_before = _ledger_state(prod_db)

        proc = _git(repo, "commit", "-m", "first commit no parent", "-q",
                    env={"PRE_COMMIT_SCORE_DB": str(db)})
        check(proc.returncode == 0,
              f"the fixture commit must succeed (rc={proc.returncode}): "
              f"{(proc.stderr or proc.stdout)[-300:]}")

        if prod_before is not None:
            check(_ledger_state(prod_db) == prod_before,
                  f"the prod ledger must be untouched by a fixture commit "
                  f"(PRE_COMMIT_SCORE_DB override not honoured?): {prod_db}")

        check(db.exists(), "the hook must score the commit into the scratch DB")
        if not db.exists():
            return
        ids = [r[0] for r in sqlite3.connect(db).execute(
            "SELECT DISTINCT task_id FROM loop_cycles")]
        check(bool(ids), "the hook must record at least one cycle")
        for tid in ids:
            check("\n" not in tid and "\r" not in tid,
                  f"task id must not carry a newline: {tid!r}")
            check(not re.search(r"\s", tid), f"task id must not carry whitespace: {tid!r}")
            check(re.fullmatch(r"precommit-[^/]+/[A-Za-z0-9._-]+", tid) is not None,
                  f"task id must keep its documented shape: {tid!r}")
        print(f"  task ids recorded: {ids}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_no_op_close_is_information_not_a_hazard()
    test_first_commit_task_id_has_no_continuation_line()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: no-op closes are informational; task ids carry no continuation line")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
