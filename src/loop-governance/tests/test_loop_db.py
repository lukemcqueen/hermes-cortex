"""Tests for loop_db.py — database CRUD operations."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLoopDB:
    def test_create_and_query(self, tmp_db):
        """Should create tables and store/retrieve cycles."""
        cid = tmp_db.log_cycle(
            task_id="test-task", cycle_num=1,
            completeness=8.0, quality=7.0, progress=9.0,
            composite=8.1, no_progress=False, decision="STOP ✓",
        )
        assert cid > 0

        cycle = tmp_db.get_cycle(cid)
        assert cycle["task_id"] == "test-task"
        assert cycle["composite"] == 8.1

    def test_get_cycles_for_task(self, seeded_db):
        cycles = seeded_db.get_cycles_for_task("feature-a")
        assert len(cycles) == 2
        assert cycles[0]["cycle_num"] == 1
        assert cycles[1]["cycle_num"] == 2

    def test_get_summary_stats(self, seeded_db):
        stats = seeded_db.get_summary_stats()
        assert stats["total_cycles"] == 5
        assert stats["user_feedback_count"] == 3
        assert stats["stop_count"] >= 2

    def test_record_user_outcome(self, tmp_db):
        cid = tmp_db.log_cycle(
            task_id="feedback-test", cycle_num=1,
            completeness=7.0, quality=6.0, progress=8.0,
            composite=7.0, no_progress=False, decision="LOOP",
        )
        tmp_db.record_user_outcome(cid, accepted=True, note="Good loop")
        cycle = tmp_db.get_cycle(cid)
        assert cycle["user_overrode"] == 0
        assert cycle["outcome_note"] == "Good loop"

        # Override
        tmp_db.record_user_outcome(cid, accepted=False, note="Should have stopped")
        cycle = tmp_db.get_cycle(cid)
        assert cycle["user_overrode"] == 1

    def test_record_config_change(self, tmp_db):
        tmp_db.record_config_change(
            config_json='{"weights": {"completeness": 0.45}}',
            diff="weights.completeness: 0.4 → 0.45"
        )
        rows = tmp_db.conn.execute(
            "SELECT * FROM config_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert rows is not None
        assert "completeness" in rows["config_json"]

    def test_no_progress_streak(self, seeded_db):
        streak = seeded_db.get_no_progress_streak("feature-c")
        assert streak == 1

    def test_get_decision_accuracy_no_feedback(self, tmp_db):
        """Without user_overrode set, accuracy should be empty."""
        accuracy = tmp_db.get_decision_accuracy()
        assert accuracy["total_feedback"] == 0

    def test_get_decision_accuracy_with_feedback(self, seeded_db):
        accuracy = seeded_db.get_decision_accuracy()
        assert accuracy["total_feedback"] == 3

    def test_content_sanitization(self, seeded_db):
        """Sanitize should redact API keys and private keys."""
        from loop_db import LoopDB
        sanitized = LoopDB.sanitize_code(
            'api_key = "sk-1234567890abcdef"\nprivate_key = "abc123"'
        )
        assert "REDACTED" in sanitized
        assert "sk-1234567890abcdef" not in sanitized

    def test_content_storage(self, seeded_db):
        """Content-addressable store should deduplicate."""
        seeded_db.store_content("abc123", "some content", "code")
        seeded_db.store_content("abc123", "some content", "code")  # duplicate
        rows = seeded_db.conn.execute(
            "SELECT COUNT(*) as c FROM content_assets WHERE hash='abc123'"
        ).fetchone()
        assert rows["c"] == 1