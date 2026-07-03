"""Integration test — full pipeline: score → log → feedback → evaluate → auto-apply."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from loop_db import LoopDB
from loop_scorer import full_score
from loop_config import get_config, update_config, get_diff, DEFAULT_CONFIG_PATH

pytestmark = pytest.mark.slow


class TestFullPipeline:
    """End-to-end test that exercises the complete loop governance pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db_path = tmp_path / "integration.db"
        self.config_path = tmp_path / "config.json"

        # Seed cycle data (simulating past cycles)
        db = LoopDB(str(self.db_path))
        cycles = [
            ("integration-task", 1, 6.0, 5.0, 8.0, 6.3, 0, "LOOP", None, ""),
            ("integration-task", 2, 7.0, 6.0, 7.0, 6.7, 0, "LOOP", 0, ""),
            ("integration-task", 3, 9.0, 8.0, 9.0, 8.7, 0, "STOP ✓", 0, "Good stop"),
            ("overridden-task", 1, 7.2, 6.5, 8.0, 7.2, 0, "STOP ✓", 1, "Too early"),
            ("overridden-task", 2, 9.5, 8.5, 9.0, 9.1, 0, "STOP ✓", 0, "Good stop"),
        ]
        for row in cycles:
            db.conn.execute("""INSERT INTO loop_cycles
                (task_id, cycle_num, completeness, quality, progress, composite,
                 no_progress, decision, user_overrode, outcome_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row)
        db.conn.commit()
        db.close()
        yield
        # Cleanup
        if os.path.exists(str(self.db_path)):
            os.unlink(str(self.db_path))

    def test_1_score_and_log(self):
        """Score a new cycle and log to the integration DB."""
        result = full_score(
            spec="Add two numbers",
            output="def add(a,b): return a+b",
            task_id="integration-task",
            cycle_num=4,
            db_path=str(self.db_path),
        )
        assert result.get("logged") is True, f"Not logged: {result}"
        assert result["composite"] >= 0
        assert result.get("warnings") is not None

    def test_2_provide_feedback(self):
        """Use LoopDB methods to accept/override cycles."""
        from loop_feedback import cmd_accept, cmd_override

        class Args:
            pass

        db = LoopDB(str(self.db_path))

        # Accept cycle 3
        args = Args()
        args.db = str(self.db_path)
        args.cycle_id = 3
        args.note = "Correct stop"
        args.force = False
        args.json = False
        cmd_accept(args)
        cycle = db.get_cycle(3)
        assert cycle["user_overrode"] == 0

        # Override cycle 1
        args2 = Args()
        args2.db = str(self.db_path)
        args2.cycle_id = 1
        args2.note = "Should have been STOP, quality was good enough"
        args2.force = False
        args2.json = False
        cmd_override(args2)
        cycle = db.get_cycle(1)
        assert cycle["user_overrode"] == 1

        db.close()

    def test_3_evaluator_generates_patch(self):
        """Evaluator should produce a structured config patch."""
        from loop_evaluator import LoopEvaluator
        ev = LoopEvaluator(db_path=str(self.db_path))
        patch = ev.generate_config_patch()
        assert "schema_version" in patch
        assert patch["confidence"] >= 0
        ev.close()

    def test_4_auto_apply_safe_changes(self):
        """Auto-apply should safely apply low-risk config changes."""
        config = get_config()
        safe_changes = {"weights": {"completeness": 0.45}}
        result = update_config(safe_changes)
        assert result["weights"]["completeness"] == 0.45
        diff = get_diff(config, result)
        assert "completeness" in diff
        # Restore
        update_config({"weights": {"completeness": 0.40}})