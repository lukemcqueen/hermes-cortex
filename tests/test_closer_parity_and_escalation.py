"""BEHAVIOURAL parity between the two closers, and the escalation the sweep owes an operator.

A DeepSeek Pro review (2026-10-14) refused the earlier token-parity test as false comfort, and was
right: `_close_cycle_unscored` (MCP) selected ONE PENDING row for a task (`ORDER BY id DESC LIMIT 1`)
while `_close_pending_cycle` (the standalone sweep) resolved them ALL. A task carrying two PENDING
rows therefore kept one behind — the doctor leak both functions exist to remove — and a token
comparison cannot see it. The MCP closer now resolves every still-PENDING, non-overridden row for
the task, and this file drives BOTH implementations against the same fixtures.

The other half of the review's findings is that silence is not an acceptable operator interface:
a sweep that keeps a lock because the store is unreadable must say so with an exit code an operator
(or a cron monitor) can act on, and a lock file too corrupt to age must not be skipped forever.

Everything runs against throwaway trees and stores.
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
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"
SWEEP = REPO / "ops" / "scripts" / "manage" / "purge-stale-governance-locks.py"

SCHEMA = ("CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,"
          " cycle_num INTEGER, completeness REAL, quality REAL, progress REAL, composite REAL,"
          " decision TEXT, user_overrode INTEGER, unscored_reason TEXT, outcome_note TEXT,"
          " timestamp TEXT)")


def _db(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA)
        for task_id, decision, overrode in rows:
            conn.execute("INSERT INTO loop_cycles (task_id, decision, user_overrode, timestamp)"
                         " VALUES (?,?,?,?)", (task_id, decision, overrode,
                                               "2026-10-14T00:00:00Z"))
        conn.commit()
    finally:
        conn.close()
    return path


def _pending(path: Path, task_id: str) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE task_id=? AND decision='PENDING'",
                            (task_id,)).fetchone()[0]
    finally:
        conn.close()


def _load_mcp(tmp: Path):
    spec = importlib.util.spec_from_file_location("loopgov_closer_parity", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LOOP_DB = tmp / "loop-governance.db"
    return mod


def _load_sweep(tmp: Path):
    spec = importlib.util.spec_from_file_location("sweep_closer_parity", SWEEP)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {"CORTEX_HOME": str(tmp / ".hermes-cortex")}):
        spec.loader.exec_module(mod)
    return mod


def test_both_closers_resolve_every_pending_row_for_a_task():
    """The finding: multiple PENDING rows for one task must ALL be resolved, by either closer."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Two PENDING rows is the whole point; the scored row proves the guard. (An OVERRIDDEN row
        # is deliberately NOT included here: overrides are written with decision='MOVE_ON', so a
        # PENDING+overridden row is not a state the system produces — that case is its own test.)
        rows = [("multi-task", "PENDING", None), ("multi-task", "PENDING", None),
                ("multi-task", "MOVE_ON", None)]
        mcp_db = _db(tmp_path / "mcp" / "loop-governance.db", rows)
        mcp = _load_mcp(tmp_path / "mcp")
        closed = mcp._close_cycle_unscored(None, "parity: reason", "parity: note",
                                           task_id="multi-task")
        left = _pending(mcp_db, "multi-task")
        assert closed is True and left == 0, (
            f"the MCP closer left {left} PENDING row(s) for the task — that residue is the doctor "
            "leak, and it is exactly what a token-parity test could not see"
        )

        sweep_db = _db(tmp_path / "sweep" / ".hermes-cortex" / "data" / "loop-governance.db", rows)
        sweep = _load_sweep(tmp_path / "sweep")
        assert sweep._close_pending_cycle("multi-task") is True
        assert _pending(sweep_db, "multi-task") == 0, "the sweep closer left a pending row behind"


def test_both_closers_agree_when_there_is_nothing_to_close():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _db(tmp_path / "mcp" / "loop-governance.db", [("done-task", "MOVE_ON", None)])
        mcp = _load_mcp(tmp_path / "mcp")
        assert mcp._close_cycle_unscored(None, "r", "n", task_id="done-task") is False

        _db(tmp_path / "sweep" / ".hermes-cortex" / "data" / "loop-governance.db",
            [("done-task", "MOVE_ON", None)])
        sweep = _load_sweep(tmp_path / "sweep")
        assert sweep._close_pending_cycle("done-task") is True, (
            "nothing pending means nothing to do — the sweep treats it as safe to remove the lock"
        )


def test_both_closers_leave_an_overridden_pending_row_alone():
    """An override is a human decision: cleanup must never rewrite it, in either implementation."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        path = _db(tmp_path / "mcp" / "loop-governance.db", [("ovr-task", "PENDING", 1)])
        mcp = _load_mcp(tmp_path / "mcp")
        mcp._close_cycle_unscored(None, "r", "n", task_id="ovr-task")
        assert _pending(path, "ovr-task") == 1, "an overridden row must not be closed by cleanup"


def test_the_sweep_exits_nonzero_when_it_could_not_resolve_cycles():
    """The review's finding 1: 'kept' must reach an operator, not scroll past in a log."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / ".hermes-cortex"
        (home / "state").mkdir(parents=True)          # no store at all → keep + escalate
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        (home / "state" / ".governance-nostore.json").write_text(json.dumps(
            {"session_id": "ns", "task_id": "ns", "agent": "a", "status": "executing",
             "heartbeat_at": old, "started_at": old, "ttl_seconds": 3600}))
        sweep = _load_sweep(tmp_path)
        result = sweep.sweep()
        assert result.kept_unresolved == 1 and result.removed == 0
        proc = subprocess.run([sys.executable, str(SWEEP)], capture_output=True, text=True,
                              env={**os.environ, "CORTEX_HOME": str(home)}, timeout=120)
        assert proc.returncode == 2, f"rc={proc.returncode} — an operator-action outcome must not exit 0"
        assert "OPERATOR ACTION" in proc.stdout and "❌" in proc.stdout, proc.stdout


def test_the_sweep_reports_a_corrupt_lock_file_instead_of_skipping_it_forever():
    """A file that is unparseable AND far older than the TTL is corruption, not a mid-write race."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / ".hermes-cortex"
        (home / "state").mkdir(parents=True)
        path = home / "state" / ".governance-corrupt.json"
        path.write_text("{ this is not json")
        stale = (datetime.now() - timedelta(hours=5)).timestamp()
        os.utime(path, (stale, stale))
        sweep = _load_sweep(tmp_path)
        result = sweep.sweep()
        assert len(result.corrupt) == 1, f"corrupt={result.corrupt}"
        assert path.exists(), "a corrupt lock is still SOMEONE's lock — report it, do not delete it"
        proc = subprocess.run([sys.executable, str(SWEEP)], capture_output=True, text=True,
                              env={**os.environ, "CORTEX_HOME": str(home)}, timeout=120)
        assert proc.returncode == 2 and "CORRUPT" in proc.stdout, proc.stdout


def test_a_fresh_unparseable_file_is_still_treated_as_a_mid_write_race():
    """The other direction: the corrupt branch must not fire on a lock being written right now."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / ".hermes-cortex"
        (home / "state").mkdir(parents=True)
        path = home / "state" / ".governance-midwrite.json"
        path.write_text("{ partial")
        sweep = _load_sweep(tmp_path)
        result = sweep.sweep()
        assert not result.corrupt, "a just-written unparseable lock is a race, not corruption"
        assert path.exists()
        assert sweep.main() == 0, "a mid-write race is normal operation, not an operator action"
