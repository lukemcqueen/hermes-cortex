"""Tests for ops/scripts/sustainability/write_test_results.py.

The script exists so "N tests pass" is an inspectable file, not a claim. The
test asserts it captures REAL suites (nonzero count), records exit codes, and
returns non-zero when a suite fails.

ISOLATED FROM THE LIVE ARTIFACT (fixed 2026-10-21, issue #213 / event #213): these tests used to
call `w.main("2026-10-10")` with the script's real output directory in effect, so every run
OVERWROTE the committed docs/evidence/briefings/test-results-2026-10-10.txt — leaving a tracked
evidence file dirty after any full-suite run, and (worse) able to be committed as a "capture" that
disagrees with the run it claims to record. The output dir is now redirected to a temp directory
for each test, the assertions moved with it, and each test asserts the COMMITTED file's mtime is
unchanged — so the isolation is verified rather than assumed. The coverage is the same: the
artifact is still produced and still asserted on, just not in the live tree.

stdlib-only (unittest).

Run: python3 tests/test_write_test_results.py
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "write_test_results.py"
COMMITTED_DIR = REPO / "docs" / "evidence" / "briefings"

_spec = importlib.util.spec_from_file_location("write_test_results", SCRIPT)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)  # pylint: disable=protected-access


class TestPythonExe(unittest.TestCase):
    def test_returns_an_existing_interpreter(self):
        exe = w.python_exe()
        self.assertTrue(Path(exe).exists(), exe)


class _IsolatedMain(unittest.TestCase):
    """Base: run main() with its output dir pointed at a temp dir, and prove the live
    artifact was not touched. A test that writes the committed file is a test that
    corrupts the evidence it exists to produce."""

    def setUp(self):
        self._orig_evid = w.EVID
        self._tmp = tempfile.TemporaryDirectory(prefix="write-test-results-")
        self.evid = Path(self._tmp.name)
        w.EVID = self.evid
        # Record what the committed artifact looked like, so the run can be shown to
        # leave it alone. Missing is a valid state to preserve too.
        self._live = COMMITTED_DIR / "test-results-2026-10-10.txt"
        self._live_before = (self._live.exists(),
                             self._live.stat().st_mtime_ns if self._live.exists() else None)

    def tearDown(self):
        w.EVID = self._orig_evid
        self._tmp.cleanup()
        after = (self._live.exists(),
                 self._live.stat().st_mtime_ns if self._live.exists() else None)
        self.assertEqual(
            after, self._live_before,
            f"the run modified the COMMITTED artifact {self._live} — the test is writing "
            "live evidence again (issue #213)")


class TestMain(_IsolatedMain):
    def test_records_real_results_and_summary(self):
        # A real date whose artifacts/suites exist.
        code = w.main("2026-10-10")
        dest = self.evid / "test-results-2026-10-10.txt"
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
            # The failing run still writes its (temp) artifact, so the file the
            # reviewer would inspect exists in the failure case too.
            self.assertTrue((self.evid / "test-results-2026-10-10.txt").exists())
        finally:
            w.SUITES = orig
            bad.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
