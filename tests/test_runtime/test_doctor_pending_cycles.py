"""Regression test: doctor PENDING-cycle check must accept planning-state locks.

Bug (2026-08-08): begin_change with a plan writes the lock with
status="planning" (loop-gov-mcp.py). The doctor's leak check only counted
locks with status=="executing" as active, so EVERY planned task's PENDING
cycle was misreported as a LEAK (FAIL) even while the task held its lock —
the doctor blocked pushes mid-task.

Fix: lock EXISTENCE is the active signal (end_change unlinks it on
release); any non-terminal status (completed/cancelled excluded) counts.

This test reproduces the exact scenario hermetically: a temp CORTEX_HOME
with a PENDING cycle whose task holds a planning-state lock. The check
must classify it as INFO (active task), never FAIL (leak).
"""

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# ── Point at hermetic homes BEFORE importing the doctor module ──
_TMP = tempfile.mkdtemp(prefix="doctor-pending-test-")
os.environ["HERMES_CORTEX_HOME"] = _TMP
os.environ["HERMES_HOME"] = os.path.join(_TMP, "hermes")

# Ensure the repo's doctor module is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


@pytest.fixture()
def seeded_home():
    """Create a PENDING cycle + planning-state lock for the same task."""
    state_dir = Path(_TMP) / "state"
    data_dir = Path(_TMP) / "data"
    state_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    db = data_dir / "loop-governance.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS loop_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, task_id TEXT, cycle_num INTEGER,
            spec_hash TEXT, code_hash TEXT, test_output_hash TEXT,
            completeness REAL, quality REAL, progress REAL, composite REAL,
            no_progress INTEGER, decision TEXT, user_overrode INTEGER,
            outcome_note TEXT, schema_version INTEGER, model_name TEXT,
            session_id TEXT)"""
    )
    conn.execute(
        "INSERT INTO loop_cycles (task_id, cycle_num, decision, timestamp) "
        "VALUES ('planned-task-xyz', 1, 'PENDING', ?)",
        (datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()

    # planning-state lock for the SAME task (what begin_change writes with a plan)
    lock = {
        "task_id": "planned-task-xyz",
        "status": "planning",
        "session_id": "cron_test_123",
        "heartbeat_at": "2026-08-08T04:00:00",
        "ttl_seconds": 3600,
    }
    (state_dir / ".governance-test_123.json").write_text(json.dumps(lock))
    yield


def _find_result(res, name):
    for r in res.checks:
        if r.get("name") == name:
            return r
    return None


def test_planning_lock_is_active_not_leak(seeded_home):
    """A PENDING cycle with a live planning-state lock must be INFO, not FAIL."""
    res = Results()
    checks.check_governance(res)

    entry = _find_result(res, "PENDING cycles")
    assert entry is not None, "PENDING cycles check did not run"
    assert entry["status"] != "FAIL", (
        f"planning-state lock misclassified as leak: {entry}"
    )
    assert entry["status"] == "INFO", (
        f"expected INFO for active planning lock, got {entry['status']}: {entry}"
    )
    assert "active-task" in entry["detail"].lower() or "lock held" in entry["detail"].lower()


def test_terminal_lock_is_leak(seeded_home):
    """A PENDING cycle with NO lock at all is a genuine leak (FAIL preserved)."""
    # Remove the lock — the PENDING cycle now has no active task
    (Path(_TMP) / "state" / ".governance-test_123.json").unlink()

    res = Results()
    checks.check_governance(res)

    entry = _find_result(res, "PENDING cycles")
    assert entry is not None
    assert entry["status"] == "FAIL", (
        f"unlocked PENDING cycle must stay FAIL, got {entry['status']}: {entry}"
    )


def test_completed_lock_is_leak(seeded_home):
    """A PENDING cycle whose lock is in a terminal state is a leak (FAIL)."""
    # Rewrite the lock with a terminal status — task is done, cycle unscored
    lock = {
        "task_id": "planned-task-xyz",
        "status": "completed",
        "session_id": "cron_test_123",
        "heartbeat_at": "2026-08-08T04:00:00",
        "ttl_seconds": 3600,
    }
    (Path(_TMP) / "state" / ".governance-test_123.json").write_text(json.dumps(lock))

    res = Results()
    checks.check_governance(res)

    entry = _find_result(res, "PENDING cycles")
    assert entry is not None
    assert entry["status"] == "FAIL", (
        f"terminal-state lock must be a leak, got {entry['status']}: {entry}"
    )
