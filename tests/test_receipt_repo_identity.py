#!/usr/bin/env python3
"""A silent receipt bail must become a REPORTED one, and the repo must be declarable.

Measured 2026-10-14: a Hermes session's lock carried no ``repo_path`` (the enforcer had
not yet learned the session's repo), so ``_write_review_receipt`` bailed, the close
returned success anyway, and ``git push`` refused the range with no way back - the lock
that could re-mint the receipt was already released. Two things are pinned here:

  1. Every bail path RETURNS a reason (the close can then report it before the push),
     and a caller holding the lock can pass it in directly - the CLEAN branch of the
     review gate has no tool-call args, so without that it could only call
     ``_read_lock(None)`` and bail, which is the same silent-failure shape as 2026-10-07.
  2. ``CORTEX_SESSION_REPO`` is honoured for a Hermes caller (a DECLARATION, not a
     guess), while the no-guessing property is preserved: with nothing declared and
     nothing injected the repo is still None, never the shared daemon's cwd.

A session id in a fixture is deliberately NOT digit-dense: an unbroken digit run reads
as a phone number to the PII guard and blocks its own commit.

Loads the REPO source, not the deployed copy, so it is runnable before a deploy.
Run: python3 -m pytest tests/test_receipt_repo_identity.py -q
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "mcp-servers" / "loop-gov-mcp.py"
_HERMES_CALLER_ARGS = {"session_id": "test-session-id"}


def _load():
    spec = importlib.util.spec_from_file_location("loop_gov_under_test", _SRC)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_bail_returns_the_reason_and_names_the_remedy():
    m = _load()
    got = m._write_review_receipt("t", None, state={})
    assert got, "a lock with no repo identity must return a reason, not None"
    assert "no repo identity" in got, got
    assert "begin_change" in got or "CORTEX_SESSION_REPO" in got, got
    print("  a repo-less lock returns a reportable reason naming the remedy ✓")


def _fixture_repo(tmp: Path) -> tuple[Path, str]:
    """A temp repo with ONE unpushed commit over a local origin/main ref.

    Hermetic on purpose: the live repo is usually level with origin, and an empty
    range is refused by the writer (correctly), so asserting on ambient state would
    flap. Returns (path, expected tip).
    """
    repo = tmp / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    run = lambda *a: subprocess.run(["git", *a], cwd=repo, env=env, check=True,
                                    capture_output=True, text=True)
    run("init", "-q", "-b", "main")
    (repo / "base.txt").write_text("base\n")
    run("add", "base.txt")
    run("commit", "-qm", "base")
    base = run("rev-parse", "HEAD").stdout.strip()
    run("update-ref", "refs/remotes/origin/main", base)
    (repo / "change.txt").write_text("change\n")
    run("add", "change.txt")
    run("commit", "-qm", "unpushed change")
    return repo, run("rev-parse", "HEAD").stdout.strip()


def test_a_resolved_lock_still_writes_a_receipt():
    m = _load()
    tmp = Path(tempfile.mkdtemp(prefix="receipt-repo-identity-"))
    real = m.GOVERNANCE_STATE_DIR
    try:
        repo, head = _fixture_repo(tmp)
        state_dir = tmp / "state"
        state_dir.mkdir()
        m.GOVERNANCE_STATE_DIR = state_dir
        got = m._write_review_receipt(
            "t", None, state={"repo_path": str(repo), "repo_slug": repo.name})
        assert got is None, got
        made = sorted(state_dir.glob(".reviewed-*.json"))
        assert len(made) == 1, made
        d = json.loads(made[0].read_text())
        assert d["tip_sha"] == head, (d["tip_sha"], head)
        assert d["base_sha"] != head, "a receipt must bind a base DIFFERENT from the tip"
        assert d["verdict"] == "CLEAN"
        assert d["reviewed_files"] == ["change.txt"], d["reviewed_files"]
    finally:
        m.GOVERNANCE_STATE_DIR = real
        shutil.rmtree(tmp, ignore_errors=True)
    print("  a lock WITH a repo writes a bound receipt and returns None ✓")


def test_a_declared_session_repo_is_honoured_for_a_hermes_caller():
    """The enforcer-injected session id marks a Hermes caller; CORTEX_SESSION_REPO is
    an explicit declaration and must still be honoured for it."""
    m = _load()
    saved = os.environ.get("CORTEX_SESSION_REPO")
    try:
        os.environ["CORTEX_SESSION_REPO"] = str(_REPO)
        got = m._session_repo_path(dict(_HERMES_CALLER_ARGS))
        assert got == _REPO, got
    finally:
        if saved is None:
            os.environ.pop("CORTEX_SESSION_REPO", None)
        else:
            os.environ["CORTEX_SESSION_REPO"] = saved
    print("  CORTEX_SESSION_REPO is honoured even for an enforcer-identified caller ✓")


def test_no_declaration_means_no_guess_for_a_hermes_caller():
    """The property the 2026-10-09 change protects: a Hermes session is never tagged
    with whatever checkout the shared daemon happens to sit in."""
    m = _load()
    saved = os.environ.get("CORTEX_SESSION_REPO")
    try:
        os.environ.pop("CORTEX_SESSION_REPO", None)
        got = m._session_repo_path(dict(_HERMES_CALLER_ARGS))
        assert got is None, f"must not guess a repo for a Hermes caller, got {got}"
    finally:
        if saved is not None:
            os.environ["CORTEX_SESSION_REPO"] = saved
    print("  no declaration + no injection still resolves to None (no guessing) ✓")


def test_a_bogus_declaration_is_rejected():
    m = _load()
    saved = os.environ.get("CORTEX_SESSION_REPO")
    try:
        os.environ["CORTEX_SESSION_REPO"] = "/nonexistent/not-a-repo"
        assert m._session_repo_path(dict(_HERMES_CALLER_ARGS)) is None
    finally:
        if saved is None:
            os.environ.pop("CORTEX_SESSION_REPO", None)
        else:
            os.environ["CORTEX_SESSION_REPO"] = saved
    print("  a declared path that is not a git repo is rejected, not trusted ✓")


def test_the_clean_branch_passes_the_lock_it_holds():
    """Source guard for the second silent-bail site: _clear_close_refused must forward
    the lock it was given, or the writer falls back to _read_lock(None)."""
    src = _SRC.read_text()
    assert '_clear_close_refused(cycle.get("id"), lock)' in src, \
        "the CLEAN branch must pass its resolved lock to the receipt writer"
    assert "_write_review_receipt(cycle_id, None, state=state)" in src, \
        "_clear_close_refused must forward state into the receipt writer"
    print("  the CLEAN branch forwards its lock instead of re-reading it with None ✓")


def _call_arguments(src: str, fn: str) -> list[str]:
    """The ARGUMENT TEXT of every ``fn(...)`` call in ``src``, definition excluded.

    Parenthesis-balanced rather than line-based: a legitimately wrapped call would
    otherwise read as a violation, and this guard exists to catch a MISSING argument,
    not a formatting choice.
    """
    out, needle = [], fn + "("
    i = src.find(needle)
    while i != -1:
        start = i + len(needle)
        if src[max(0, i - 4):i] != "def ":
            depth, j = 1, start
            while j < len(src) and depth:
                if src[j] == "(":
                    depth += 1
                elif src[j] == ")":
                    depth -= 1
                j += 1
            out.append(src[start:j - 1])
        i = src.find(needle, i + len(needle))
    return out


def test_every_refusal_marker_site_passes_the_resolved_lock():
    """The SAME bug class, one function away (found by an external review 2026-10-14).

    `_mark_close_refused` also called `_read_lock(None)`, so the marker that tells the
    next change "you are committing on top of a REFUSED close" was never written for a
    Hermes session — the one state the design exists to make visible. Every call site
    already holds the lock, so every call site must pass it.
    """
    src = _SRC.read_text()
    calls = _call_arguments(src, "_mark_close_refused")
    assert calls, "expected the refusal marker call sites to exist"
    bad = [c for c in calls if not c.replace("\n", " ").strip().endswith("lock")]
    assert not bad, f"these sites would fall back to _read_lock(None): {bad}"
    print(f"  all {len(calls)} refusal-marker sites pass the resolved lock ✓")


def test_the_refusal_marker_lands_in_the_callers_lock(tmp_path):
    """Behavioural, not source-level: the marker must be written to the lock the caller
    resolved, and must NOT create governance state inside the repo."""
    m = _load()
    real = m.GOVERNANCE_STATE_DIR
    try:
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        repo = tmp_path / "repo"
        repo.mkdir()
        m.GOVERNANCE_STATE_DIR = state_dir
        lock = {"session_id": "test-session-id", "repo_path": str(repo), "repo_slug": "r"}
        m._mark_close_refused(999, "FINDINGS", json.dumps([{"finding_id": "f1"}]), state=lock)
        made = sorted(state_dir.glob(".governance-*.json"))
        assert len(made) == 1, f"the marker must be written to the resolved lock: {made}"
        d = json.loads(made[0].read_text())
        assert d["close_refused"]["cycle_id"] == 999, d
        assert d["close_refused"]["verdict"] == "FINDINGS", d
        assert not list(repo.rglob("*")), "no governance state may be created inside a repo"
    finally:
        m.GOVERNANCE_STATE_DIR = real
    print("  the refusal marker lands in the caller's lock, and never in the repo ✓")


def test_the_clean_branch_reports_a_bail_instead_of_swallowing_it():
    """`_clear_close_refused` discarding the writer's return value is the same silence
    the report-and-remedy work removed everywhere else: a CLEAN close whose receipt
    could not be written must say so."""
    m = _load()
    got = m._clear_close_refused(999, state={"session_id": "test-session-id"})
    assert got, "the CLEAN branch must not discard the receipt writer's bail reason"
    assert "no repo identity" in got, got
    print("  the CLEAN branch returns the bail reason instead of discarding it ✓")


def test_the_receipt_shape_is_unchanged_by_a_second_write(tmp_path):
    """Idempotence: the CLEAN branch and the close path both write a receipt for the
    same range, so the second write must not corrupt or double the first."""
    m = _load()
    real = m.GOVERNANCE_STATE_DIR
    try:
        repo, head = _fixture_repo(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        m.GOVERNANCE_STATE_DIR = state_dir
        lock = {"repo_path": str(repo), "repo_slug": repo.name,
                "session_id": "test-session-id"}
        assert m._write_review_receipt("t", None, state=lock) is None
        assert m._write_review_receipt("t", None, state=lock) is None
        made = sorted(state_dir.glob(".reviewed-*.json"))
        assert len(made) == 1, f"one range must produce ONE receipt file, got {made}"
        assert json.loads(made[0].read_text())["tip_sha"] == head
    finally:
        m.GOVERNANCE_STATE_DIR = real
        shutil.rmtree(tmp_path, ignore_errors=True)
    print("  a second receipt write for the same range is idempotent ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
