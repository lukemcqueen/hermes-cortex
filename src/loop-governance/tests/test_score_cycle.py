"""Tests for score_cycle.py — CLI integration."""
import json
import os
import subprocess
import sys
import pytest

SCORE_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "score_cycle.py")


class TestScoreCycle:
    def run(self, *args):
        cmd = [sys.executable, SCORE_SCRIPT] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout + result.stderr, result.returncode

    def test_minimal_inline(self):
        out, rc = self.run(
            "--task", "test-score-cycle", "--cycle", "1",
            "--code", "def f(): return 1",
            "--json",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["composite"] >= 0
        assert data["task_id"] == "test-score-cycle"
        assert data["cycle_num"] == 1
        assert "cycle_id" in data

    def test_requires_at_least_one_data_source(self):
        out, rc = self.run("--task", "empty-test", "--cycle", "1", "--json")
        assert rc != 0

    def test_logs_to_db(self):
        out, rc = self.run(
            "--task", "test-log-check", "--cycle", "1",
            "--code", "def f(): return 1",
            "--test-output", "1 passed",
            "--pass-pct", "1.0",
            "--json",
        )
        data = json.loads(out)
        assert data["logged"] is True
        assert data["cycle_id"] is not None

    def test_file_based_input(self, tmp_path):
        code_file = tmp_path / "code.py"
        code_file.write_text("def add(a,b): return a+b")
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("Add two numbers")
        test_file = tmp_path / "test.txt"
        test_file.write_text("1 passed, 0 failed")

        out, rc = self.run(
            "--task", "test-file-input", "--cycle", "1",
            "--code-file", str(code_file),
            "--spec-file", str(spec_file),
            "--test-file", str(test_file),
            "--pass-pct", "1.0",
            "--json",
        )
        assert rc == 0
        data = json.loads(out)
        assert data["logged"] is True

    def test_prev_code_for_progress(self, tmp_path):
        code_file = tmp_path / "v2.py"
        code_file.write_text("def add(a,b): return a + b  # v2 with docs")
        prev_file = tmp_path / "v1.py"
        prev_file.write_text("def add(a,b): return a+b")

        out, rc = self.run(
            "--task", "test-progress", "--cycle", "2",
            "--code-file", str(code_file),
            "--prev-code-file", str(prev_file),
            "--json",
        )
        assert rc == 0
        data = json.loads(out)
        # Progress should be detectable between v1 and v2
        assert data["progress"] >= 0