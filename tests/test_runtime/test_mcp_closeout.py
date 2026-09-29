"""
MCP Close-Out Test Suite — score before moving to a new task (2026-08-08).

Luke directive: agents must close out/score before moving to a new task.
Regression coverage for the two enforcement upgrades in
mcp-servers/loop-gov-mcp.py:

  1. end_change() BLOCKS releasing the lock while the task's cycle is
     unscored (was: warning-only, lock released anyway → PENDING leak).
  2. begin_change() REFUSES a new task while this session still holds
     unscored PENDING cycles from earlier tasks (was: only the lock was
     checked → a session could stack unbounded PENDING cycles).

The proof-of-bug sequence that motivated this: begin(A) → end(A) unscored
(lock released, cycle PENDING) → begin(B) succeeded → two PENDING cycles
for one session, only caught later by the doctor at push time.
"""

import importlib.util
import os
import tempfile
from pathlib import Path

import pytest

_MCP_PATH = Path(__file__).resolve().parents[2] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)


@pytest.fixture
def isolated():
    """Repoint the MCP module's DB + state dir to a temp sandbox."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        originals = {
            "LOOP_DB": mcp.LOOP_DB,
            "CONFIG_PATH": mcp.CONFIG_PATH,
            "CACHE_DB": mcp.CACHE_DB,
            "GOVERNANCE_STATE_DIR": mcp.GOVERNANCE_STATE_DIR,
            "FORCE_AUDIT_PATH": mcp.FORCE_AUDIT_PATH,
            "HOME": mcp.HOME,
        }
        mcp.LOOP_DB = tmp / "loop.db"
        mcp.CONFIG_PATH = tmp / "config.json"
        mcp.CACHE_DB = tmp / "cache.db"
        mcp.GOVERNANCE_STATE_DIR = tmp / "state"
        mcp.FORCE_AUDIT_PATH = mcp.GOVERNANCE_STATE_DIR / "force-acquire-audit.json"
        # Isolate from the real deployed-vs-repo dogfood check
        mcp._require_dogfood = lambda: None
        # Isolate the complexity/adversarial review from the REAL repo:
        # give the sandbox its own tiny governed repo so the reviewer never
        # diffs this working tree (its 20-file mid-session diff made the
        # review fail on unrelated evidence-mismatch findings).
        import subprocess as sp
        repo = tmp / "hermes-cortex"
        repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
            sp.run(argv, cwd=repo, env=env, check=True, capture_output=True)
        (repo / "readme.txt").write_text("tiny sandbox change\n")
        sp.run(["git", "add", "-A"], cwd=repo, env=env, check=True, capture_output=True)
        sp.run(["git", "commit", "-qm", "tiny"], cwd=repo, env=env, check=True, capture_output=True)
        mcp.HOME = tmp
        yield tmp
        for k, v in originals.items():
            setattr(mcp, k, v)


def _pending_cycles(session_id: str):
    conn = mcp._db()
    rows = conn.execute(
        "SELECT id, task_id FROM loop_cycles "
        "WHERE session_id = ? AND decision = 'PENDING' AND user_overrode IS NULL",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


class TestEndChangeRequiresScoredCycle:
    def test_unscored_end_change_blocks_and_keeps_lock(self, isolated):
        args = {"session_id": "sess_1"}
        mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        result = mcp._end_change({"task_id": "task-A", **args})
        text = result.content[0].text
        assert "Cannot release lock" in text, text
        assert "NOT scored" in text, text
        # Lock must still be held
        assert (isolated / "state" / ".governance-sess_1.json").exists()

    def test_scored_end_change_releases(self, isolated):
        args = {"session_id": "sess_2"}
        mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        conn = mcp._db()
        row = conn.execute("SELECT id FROM loop_cycles WHERE task_id='task-A' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        mcp._feedback_accept({"cycle_id": row[0],
                              "note": "verified: pytest tests/test_x.py -q -> '1 passed in 0.02s'; "
                                      "diff: ops/scripts/foo.py (+3/-1) adds retry with timeout=5",
                              "completeness": 10, "quality": 9, "progress": 8, **args})
        result = mcp._end_change({"task_id": "task-A", **args})
        text = result.content[0].text
        assert "closed" in text, text
        assert not (isolated / "state" / ".governance-sess_2.json").exists()

    def test_override_with_reason_releases(self, isolated):
        """An override also has to leave a closed-out record (2026-09-23):
        a decision correction is not a measurement, so it carries the reason."""
        args = {"session_id": "sess_3"}
        mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        conn = mcp._db()
        row = conn.execute("SELECT id FROM loop_cycles WHERE task_id='task-A' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        mcp._feedback_override({"cycle_id": row[0], "correct_decision": "STOP",
                                "note": "spike: ran python3 spike.py --dry-run -> 'dry-run ok, 0 writes'; "
                                        "diff: none committed (throwaway prototype, discarded)",
                                "unscored_reason": "spike discarded — nothing to measure",
                                **args})
        result = mcp._end_change({"task_id": "task-A", **args})
        assert "closed" in result.content[0].text


class TestBeginChangeCloseOutGate:
    def test_begin_new_task_refused_while_prior_pending(self, isolated):
        """The leak sequence: end(A) unscored is now impossible (blocked),
        but test the defensive gate directly: simulate a prior PENDING cycle
        (e.g. pre-fix leftover) and verify begin_change refuses."""
        args = {"session_id": "sess_4"}
        mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        # Force-release A's lock WITHOUT scoring (simulating a pre-fix leak)
        mcp._release_lock(args)
        result = mcp._begin_change({"task_id": "task-B", "description": "test B", **args})
        text = result.content[0].text
        assert "Close out your previous task" in text, text
        assert "task-A" in text
        # No new lock, no new cycle
        assert not (isolated / "state" / ".governance-sess_4.json").exists()
        pending = _pending_cycles("sess_4")
        assert len(pending) == 1 and pending[0]["task_id"] == "task-A"

    def test_begin_allowed_after_scoring_prior(self, isolated):
        args = {"session_id": "sess_5"}
        mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        mcp._release_lock(args)
        # Score A, then B is allowed
        conn = mcp._db()
        row = conn.execute("SELECT id FROM loop_cycles WHERE task_id='task-A' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        mcp._feedback_accept({"cycle_id": row[0], "note": "done",
                              "completeness": 10, "quality": 8, "progress": 9, **args})
        result = mcp._begin_change({"task_id": "task-B", "description": "test B", **args})
        assert "Governance session started" in result.content[0].text
        # cleanup
        conn = mcp._db()
        row = conn.execute("SELECT id FROM loop_cycles WHERE task_id='task-B' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        mcp._feedback_accept({"cycle_id": row[0], "note": "done",
                              "completeness": 10, "quality": 8, "progress": 9, **args})
        mcp._end_change({"task_id": "task-B", **args})

    def test_hook_cycles_do_not_trip_gate(self, isolated):
        """Pre-commit hook cycles carry session_id NULL — they must never
        block an interactive session's begin_change."""
        args = {"session_id": "sess_6"}
        conn = mcp._db()
        conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, progress, composite, no_progress, decision, user_overrode, session_id) "
            "VALUES ('precommit-repo-main/some-subject', 1, 0, 0, 0, 0, 0, 'LOOP', NULL, NULL)"
        )
        conn.commit()
        conn.close()
        result = mcp._begin_change({"task_id": "task-A", "description": "test A", **args})
        assert "Governance session started" in result.content[0].text
        # cleanup
        conn = mcp._db()
        row = conn.execute("SELECT id FROM loop_cycles WHERE task_id='task-A' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        mcp._feedback_accept({"cycle_id": row[0], "note": "done",
                              "completeness": 10, "quality": 8, "progress": 9, **args})
        mcp._end_change({"task_id": "task-A", **args})
