#!/usr/bin/env python3
"""A lock that names NO repo must not authorise anything, and must not be a dead end.

Four defects found by an external review of the governance plumbing (2026-10-14):

1. `_promote_issue_to_task` mints a lock whose state dict carries no repo_path or
   repo_slug, so end_change refuses it ("no governed repo to measure complexity") and the
   cycle it creates cannot be closed by the normal path. (It also creates no claimable
   task row — tracked separately.)
2. The enforcer's staleness rule floors the TTL at 7200s (`max(ttl, max_age)`) while the
   MCP server treats the lock's own 3600s TTL as authoritative. So "TTL: 3600s", the number
   the operator is shown, is NOT the blocking horizon: one component calls the lock expired
   while the other still honours it.
3. The enforcer's Phase-2 repo match lets `repo_slug is None` match the CURRENT repo — a
   latent fail-open, masked today only because the session match usually skips a foreign
   lock first. Any lock that names no repo could authorise writes in whatever repository
   the same session touched next.
4. The refusal a blocked session sees must name the way out: a lock that can never be
   closed by end_change is released by a TERMINAL task state, and nothing says so.

These drive the real functions (`_promote_issue_to_task` with `_write_lock`/`_db`
captured, `_has_governance_lock` against a temp state dir with a real lock file).

Run: python3 -m pytest tests/test_repo_less_lock_handling.py -q
"""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_GOV = _REPO / "mcp-servers" / "loop-gov-mcp.py"
_ENF = _REPO / "plugins" / "governance-enforcer" / "__init__.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Dead:
    """A DB handle that fails every call: the handler's DB writes are all wrapped, and
    this test is about the STATE DICT it builds, not the rows it inserts."""

    def execute(self, *a, **k):
        raise RuntimeError("no schema in this test")

    def commit(self):
        pass

    def close(self):
        pass


def test_the_promotion_lock_records_the_repo(monkeypatch):
    m = _load(_GOV, "gov_promote")
    captured = {}
    m._write_lock = lambda state, args=None: captured.update(state)
    m._db = lambda: _Dead()
    saved = os.environ.get("CORTEX_SESSION_REPO")
    os.environ["CORTEX_SESSION_REPO"] = str(_REPO)
    try:
        m._promote_issue_to_task({"task_id": "promoted-placeholder",
                                  "description": "regression placeholder",
                                  "issue_event_id": None, "ttl": 3600})
    finally:
        if saved is None:
            os.environ.pop("CORTEX_SESSION_REPO", None)
        else:
            os.environ["CORTEX_SESSION_REPO"] = saved
    assert captured, "the handler must still write a lock"
    assert captured.get("repo_path"), (
        "a promotion lock with no repo_path cannot be closed by end_change: " + repr(captured))
    assert captured.get("repo_slug"), (
        "a repo-less lock matches ANY repo in the enforcer's Phase 2: " + repr(captured))
    print("  the promotion lock records the repo it belongs to OK")


def test_the_enforcer_uses_the_locks_own_ttl():
    e = _load(_ENF, "enforcer_ttl")
    hb = (datetime.now(timezone.utc) - timedelta(seconds=4000)).replace(tzinfo=None).isoformat()
    state = {"task_id": "t", "ttl_seconds": 3600, "heartbeat_at": hb}
    assert e._is_lock_stale(state) is True, (
        "a lock whose own 3600s TTL elapsed 4000s ago is stale to the MCP server, so the "
        "enforcer must agree — otherwise the advertised TTL is not the blocking horizon")
    fresh = dict(state, heartbeat_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
    assert e._is_lock_stale(fresh) is False, "a fresh lock must never be stale"
    print("  the enforcer honours the lock's own TTL, both directions OK")


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    return repo


def test_a_repo_less_lock_does_not_authorise_a_repo(tmp_path):
    e = _load(_ENF, "enforcer_phase2")
    target = _git_repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    hb = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    (state_dir / ".governance-sess-a.json").write_text(json.dumps({
        "task_id": "promoted-placeholder", "session_id": "sess-a",
        "heartbeat_at": hb, "ttl_seconds": 3600,  # NOTE: no repo_path, no repo_slug
    }))
    e.GOVERNANCE_STATE_DIR = state_dir
    got = e._has_governance_lock("sess-a", str(target))
    assert got is False, (
        "a lock that names no repo must never authorise writes in a repo it does not name "
        "(latent fail-open): the same session could write anywhere")
    print("  a repo-less lock does not authorise a repo it does not name OK")


def test_a_repo_naming_lock_still_authorises_its_own_repo(tmp_path):
    """The both-ways half: the guard must not disarm a legitimate lock."""
    e = _load(_ENF, "enforcer_phase2_ok")
    target = _git_repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    hb = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    (state_dir / ".governance-sess-b.json").write_text(json.dumps({
        "task_id": "real-work", "session_id": "sess-b", "repo_path": str(target),
        "repo_slug": target.name, "heartbeat_at": hb, "ttl_seconds": 3600,
    }))
    e.GOVERNANCE_STATE_DIR = state_dir
    assert e._has_governance_lock("sess-b", str(target)) is True, (
        "a lock naming THIS repo must still authorise writes in it")
    print("  a lock that names its repo still authorises it OK")


def test_the_refusal_names_the_way_out():
    """Unit test of the refusal MESSAGE, both directions.

    It is driven directly because the gates that precede it (dogfood, unscored PENDING
    cycles) query live state: a test that must defeat two unrelated gates to read one
    message has a verdict that depends on the host, not on the message.
    """
    m = _load(_GOV, "gov_refusal")
    repo_less = m._active_lock_refusal_text({
        "task_id": "repo-less-placeholder", "description": "a placeholder",
        "session_id": "s", "started_at": "t", "heartbeat_at": "t", "agent": "a"})
    assert "advance_task_state" in repo_less and "new_state='cancelled'" in repo_less, (
        "a repo-less lock cannot be closed by end_change, so the refusal must name the "
        "release that works: " + repo_less)
    assert "never goes stale" in repo_less, (
        "and it must say why waiting does not help: " + repo_less)
    normal = m._active_lock_refusal_text({
        "task_id": "real-work", "description": "d", "repo_path": "/some/repo",
        "repo_slug": "some-repo", "session_id": "s", "started_at": "t",
        "heartbeat_at": "t", "agent": "a"})
    assert "end_change('real-work')" in normal, normal
    assert "advance_task_state" not in normal, (
        "a normal lock must keep the ordinary advice: " + normal)
    print("  the refusal names the terminal-state release only when it is needed OK")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
