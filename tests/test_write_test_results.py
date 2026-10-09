"""Tests for ops/scripts/sustainability/write_test_results.py.

The script exists so "N tests pass" is an inspectable file, not a claim. The
test asserts it captures REAL suites (nonzero count), records exit codes, and
returns non-zero when a suite fails.

stdlib-only (unittest).

Run: python3 tests/test_write_test_results.py
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "write_test_results.py"

_spec = importlib.util.spec_from_file_location("write_test_results", SCRIPT)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)  # pylint: disable=protected-access


class TestPythonExe(unittest.TestCase):
    def test_returns_an_existing_interpreter(self):
        exe = w.python_exe()
        self.assertTrue(Path(exe).exists(), exe)


class TestMain(unittest.TestCase):
    def test_records_real_results_and_summary(self):
        # A real date whose artifacts/suites exist.
        code = w.main("2026-10-10")
        dest = REPO / "docs" / "evidence" / "briefings" / (
            "test-results-2026-10-10.txt")
        self.assertTrue(dest.exists())
        text = dest.read_text(encoding="utf-8")
        self.assertIn("SUMMARY:", text)
        self.assertIn("exit_code=", text)
        self.assertIn("test_gen_briefing.py", text)
        # 12 + 6 + 5 + (verify_briefing suite) > 20; assert a real number,
        # not a placeholder zero.
        summary = [ln for ln in text.splitlines()
                   if ln.startswith("SUMMARY:")][-1]
        count = int(summary.split()[1])
        self.assertGreater(count, 20, summary)
        self.assertIn("failing suites: 0", summary)
        self.assertEqual(code, 0)

    def test_returns_failure_when_a_suite_fails(self):
        # Point the suite list at a deliberately failing module for one run.
        orig = w.SUITES
        bad = REPO / "tests" / "_tmp_failing_suite_for_test.py"
        bad.write_text("import unittest\n"
                       "class T(unittest.TestCase):\n"
                       "    def test_x(self):\n"
                       "        self.fail('intentional')\n"
                       "unittest.main()\n", encoding="utf-8")
        w.SUITES = ("tests/_tmp_failing_suite_for_test.py",)
        try:
            rc = w.main("2026-10-10")
            self.assertEqual(rc, 1, "a failing suite must return non-zero")
        finally:
            w.SUITES = orig
            bad.unlink(missing_ok=True)
            # restore the good results file so the committed artifact is real
            w.main("2026-10-10")


if __name__ == "__main__":
    unittest.main()
