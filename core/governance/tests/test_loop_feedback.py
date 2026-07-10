"""Tests for loop_feedback.py — accept/override/force behavior."""
import json
import os
import subprocess
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from loop_db import LoopDB

FEEDBACK_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "loop_feedback.py")


@pytest.fixture(scope="function")
def feedback_db(tmp_path):
    """Create a DB with seeded cycles at a real path (CLI needs file path)."""
    db_path = tmp_path / "feedback-test.db"
    db = LoopDB(str(db_path))

    # Seed with actual cycles via log_cycle (not raw SQL) to get proper schema
    db.log_cycle(task_id="feature-a", cycle_num=1, completeness=6.5, quality=5.0,
                 progress=7.0, composite=6.0, no_progress=False, decision="LOOP 🔄")
    db.log_cycle(task_id="feature-a", cycle_num=2, completeness=8.5, quality=7.0,
                 progress=8.0, composite=8.0, no_progress=False, decision="STOP ✓")
    db.log_cycle(task_id="feature-b", cycle_num=1, completeness=7.0, quality=6.0,
                 progress=9.0, composite=7.2, no_progress=False, decision="STOP ✓")
    db.log_cycle(task_id="feature-c", cycle_num=1, completeness=2.0, quality=2.0,
                 progress=1.0, composite=1.5, no_progress=True, decision="STOP ✗")
    db.close()
    return str(db_path)


class TestFeedbackCLI:
    def run(self, db_path, *args):
        cmd = [sys.executable, FEEDBACK_SCRIPT, "--db", db_path] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout + result.stderr, result.returncode

    def test_list_shows_pending(self, feedback_db):
        out, rc = self.run(feedback_db, "list", "--json")
        assert rc == 0, f"STDERR: {out}"
        data = json.loads(out)
        assert len(data) == 4
        # All cycles should need feedback (user_overrode is NULL)
        for c in data:
            assert c["user_overrode"] is None

    def test_accept(self, feedback_db):
        out, rc = self.run(feedback_db, "accept", "1", "--note", "Accepting this loop")
        assert rc == 0, f"STDERR: {out}"
        assert "ACCEPTED" in out

        # Verify
        db = LoopDB(feedback_db)
        cycle = db.get_cycle(1)
        assert cycle["user_overrode"] == 0
        assert cycle["outcome_note"] == "Accepting this loop"
        db.close()

    def test_override(self, feedback_db):
        out, rc = self.run(feedback_db, "override", "2", "--note", "Should have kept looping")
        assert rc == 0, f"STDERR: {out}"
        assert "OVERRIDDEN" in out

        db = LoopDB(feedback_db)
        cycle = db.get_cycle(2)
        assert cycle["user_overrode"] == 1
        db.close()

    def test_duplicate_feedback_warning(self, feedback_db):
        self.run(feedback_db, "accept", "1", "--note", "First")
        out, rc = self.run(feedback_db, "accept", "1", "--note", "Second")
        assert "already has feedback" in out.lower()

    def test_force_overwrite(self, feedback_db):
        self.run(feedback_db, "accept", "1", "--note", "First")
        out, rc = self.run(feedback_db, "accept", "1", "--force", "--note", "Overwritten")
        assert "ACCEPTED" in out

    def test_stats_shows_counts(self, feedback_db):
        self.run(feedback_db, "accept", "1", "--note", "Good")
        out, rc = self.run(feedback_db, "stats")
        assert rc == 0
        assert "Feedback Statistics" in out or "Total" in out

    def test_stats_json(self, feedback_db):
        self.run(feedback_db, "accept", "1", "--note", "Good")
        out, rc = self.run(feedback_db, "stats", "--json")
        assert rc == 0
        data = json.loads(out)
        assert "total_cycles" in data

    def test_unknown_cycle(self, feedback_db):
        out, rc = self.run(feedback_db, "accept", "999")
        assert "not found" in out