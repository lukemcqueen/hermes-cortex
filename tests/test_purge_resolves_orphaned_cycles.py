"""The TTL sweep must not create the leak it exists to clear (#125), nor purge a busy session.

Two defects are pinned here, both measured before the fix:

  * #125 — removing a lock FILE resolved no cycle, so an abandoned session's still-PENDING row
    (younger than the doctor's 24h auto-resolve window) became a LEAK: the host FAILs the
    PENDING-cycles check and blocks EVERY agent's push, with no owner left to clear it.
  * the sweep's staleness rule was TTL-only, while the fleet's has a liveness rescue — so this
    script alone would remove a BUSY session's lock, and that session's next write is refused.

Every case runs against a throwaway CORTEX_HOME (state dir + store), so no live lock or cycle can
be touched. Both directions are covered for each guard: the case it must act on, and the case it
must stay silent on.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "manage" / "purge-stale-governance-locks.py"
MOD = REPO / "mcp-servers" / "loop-gov-mcp.py"

SCHEMA = """
CREATE TABLE loop_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    cycle_num INTEGER DEFAULT 1,
    completeness REAL, quality REAL, progress REAL, composite REAL,
    decision TEXT, user_overrode INTEGER,
    unscored_reason TEXT, outcome_note TEXT,
    timestamp TEXT
)
"""


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _cortex_home(tmp: Path, with_db: bool = True) -> Path:
    home = tmp / ".hermes-cortex"
    (home / "state").mkdir(parents=True, exist_ok=True)
    if with_db:
        (home / "data").mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(home / "data" / "loop-governance.db"))
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
    return home


def _load(home: Path):
    """Import the script with CORTEX_HOME pointed at `home` — its paths resolve at import."""
    spec = importlib.util.spec_from_file_location("purge_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {"CORTEX_HOME": str(home)}):
        spec.loader.exec_module(mod)
    return mod


def _lock(home: Path, task_id: str = "sweep-task", agent: str = "sweep-agent",
          repo_path: str = "/nonexistent-repo", minutes_ago: int = 180) -> Path:
    p = home / "state" / f".governance-{task_id}.json"
    hb = _iso(minutes_ago)
    p.write_text(json.dumps({
        "session_id": task_id, "task_id": task_id, "agent": agent, "status": "executing",
        "started_at": hb, "heartbeat_at": hb, "ttl_seconds": 3600, "repo_path": repo_path,
    }))
    return p


def _cycle(home: Path, task_id: str, decision: str = "PENDING") -> None:
    conn = sqlite3.connect(str(home / "data" / "loop-governance.db"))
    try:
        conn.execute(
            "INSERT INTO loop_cycles (task_id, decision, user_overrode, timestamp) VALUES (?,?,?,?)",
            (task_id, decision, None, _iso(30)))
        conn.commit()
    finally:
        conn.close()


def _rows(home: Path, task_id: str):
    conn = sqlite3.connect(str(home / "data" / "loop-governance.db"))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT decision, unscored_reason, outcome_note FROM loop_cycles WHERE task_id=?",
            (task_id,)).fetchall()]
    finally:
        conn.close()


def test_the_sweep_resolves_the_cycle_it_orphans():
    """#125: the lock goes AND the cycle is resolved — no lockless PENDING row is created."""
    with tempfile.TemporaryDirectory() as tmp:
        home = _cortex_home(Path(tmp))
        lock = _lock(home)
        _cycle(home, "sweep-task")
        removed = _load(home).purge()
        assert removed == 1, f"removed={removed}"
        assert not lock.exists(), "the stale lock should have been removed"
        rows = _rows(home, "sweep-task")
        assert rows[0]["decision"] == "MOVE_ON", (
            "the cycle was left PENDING while its lock was removed — that is the doctor FAIL that "
            "blocks every push on the host"
        )
        assert rows[0]["unscored_reason"], "an unscored resolution must record WHY"
        assert rows[0]["outcome_note"], "an unscored resolution must record its outcome note"


def test_the_sweep_keeps_the_lock_when_the_cycle_cannot_be_resolved():
    """Fail closed: no store to resolve against → the lock STAYS (a stale lock is harmless)."""
    with tempfile.TemporaryDirectory() as tmp:
        home = _cortex_home(Path(tmp), with_db=False)
        lock = _lock(home)
        removed = _load(home).purge()
        assert removed == 0, f"removed={removed} — a removal here creates a lockless PENDING cycle"
        assert lock.exists(), "the lock must be kept when its cycle cannot be confirmed resolved"


def test_the_sweep_still_removes_a_lock_with_nothing_pending():
    """The guard must not stop the sweep doing its job."""
    with tempfile.TemporaryDirectory() as tmp:
        home = _cortex_home(Path(tmp))
        lock = _lock(home)
        _cycle(home, "sweep-task", decision="MOVE_ON")   # already resolved
        removed = _load(home).purge()
        assert removed == 1 and not lock.exists(), f"removed={removed}"


def test_the_sweep_does_not_purge_a_lock_whose_agent_committed_since():
    """The liveness rescue the fleet has and this script lacked: a busy session is not dead."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = _cortex_home(tmp_path)
        work = tmp_path / "own-repo"
        work.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "-c", "user.name=busy-agent", "-c", "user.email=busy@example.com",
                        "commit", "-q", "--allow-empty", "-m", "work"], cwd=work, check=True)
        lock = _lock(home, task_id="busy-task", agent="busy-agent", repo_path=str(work),
                     minutes_ago=120)
        _cycle(home, "busy-task")
        removed = _load(home).purge()
        assert lock.exists(), "a lock whose agent committed since the heartbeat must not be purged"
        assert removed == 0, f"removed={removed}"
        assert _rows(home, "busy-task")[0]["decision"] == "PENDING", (
            "nothing should have been resolved — the sweep kept the lock, so the session is intact"
        )


def test_the_sweep_removes_a_lock_whose_agent_committed_only_before_the_heartbeat():
    """The other direction: the rescue must not keep every lock that ever saw a commit."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = _cortex_home(tmp_path)
        work = tmp_path / "old-repo"
        work.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        # A STRICT ISO timestamp: this git rejects approxidate ("3 hours ago") in the env dates.
        three_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00")
        old_env = {**os.environ, "GIT_AUTHOR_DATE": three_hours_ago,
                   "GIT_COMMITTER_DATE": three_hours_ago}
        subprocess.run(["git", "-c", "user.name=idle-agent", "-c", "user.email=idle@example.com",
                        "commit", "-q", "--allow-empty", "-m", "old work"],
                       cwd=work, check=True, env=old_env)
        lock = _lock(home, task_id="idle-task", agent="idle-agent", repo_path=str(work),
                     minutes_ago=60)
        _cycle(home, "idle-task")
        removed = _load(home).purge()
        assert removed == 1 and not lock.exists(), (
            "a lock whose agent's only commit predates the heartbeat is genuinely idle"
        )
        assert _rows(home, "idle-task")[0]["decision"] == "MOVE_ON"


def test_the_rescue_and_the_closer_match_the_fleet_implementations():
    """Parity: two copies of a rule drift. Assert the SAME tokens on both sides."""
    script = SCRIPT.read_text(encoding="utf-8")
    mcp = MOD.read_text(encoding="utf-8")
    # the closer: same guard, same target decision, same two fact columns
    for token in ("decision='MOVE_ON'", "decision='PENDING'", "user_overrode IS NULL",
                  "unscored_reason", "outcome_note"):
        assert token in script, f"the sweep's closer lost {token!r}"
        assert token in mcp, f"the MCP's shared closer no longer carries {token!r}"
    # the liveness rescue: same git query shape on both sides
    for token in ('"--since=" +', '"--author=" +', '"--format=%H"', "-n\", \"1\""):
        assert token in script, f"the sweep's liveness rescue lost {token!r}"
        assert token in mcp, f"the MCP's liveness rescue no longer uses {token!r}"
    # and the mtime fallback both implementations rely on for unparseable heartbeats
    assert "mtime_fallback" in script and "mtime_fallback" in mcp
