"""Tests for vacuum_old_cycles — DB retention policy."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestVaccum:
    def test_vacuum_removes_old_cycles(self, tmp_path):
        from loop_db import LoopDB

        db_path = tmp_path / "retention.db"
        db = LoopDB(str(db_path))

        # Insert a cycle with an old timestamp
        db.conn.execute("""
            INSERT INTO loop_cycles
                (task_id, cycle_num, completeness, quality, progress, composite,
                 no_progress, decision, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-100 days'))
        """, ("old-task", 1, 8.0, 7.0, 9.0, 8.1, 0, "STOP ✓"))
        db.conn.commit()

        # Insert a recent cycle
        db.log_cycle(task_id="new-task", cycle_num=1, completeness=8.0, quality=7.0,
                     progress=9.0, composite=8.1, no_progress=False, decision="STOP ✓")

        archive_dir = tmp_path / "archive"
        result = db.vacuum_old_cycles(days=30, archive_dir=str(archive_dir))

        assert result["archived"] == 1, f"Expected 1 old cycle archived, got {result}"
        assert os.path.exists(result["archive_path"])

        # Only the new cycle should remain
        remaining = db.conn.execute("SELECT COUNT(*) AS c FROM loop_cycles").fetchone()["c"]
        assert remaining == 1

        db.close()

    def test_vacuum_no_old_cycles(self, tmp_path):
        from loop_db import LoopDB

        db_path = tmp_path / "empty-retention.db"
        db = LoopDB(str(db_path))
        db.log_cycle(task_id="recent", cycle_num=1, completeness=8.0, quality=7.0,
                     progress=9.0, composite=8.1, no_progress=False, decision="STOP ✓")

        result = db.vacuum_old_cycles(days=90, archive_dir=str(tmp_path / "archive"))
        assert result["archived"] == 0

        db.close()