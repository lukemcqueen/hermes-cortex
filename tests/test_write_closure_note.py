"""Tests for ops/scripts/sustainability/write_closure_note.py.

The note exists to answer reviewer findings with git facts. The test asserts
it emits the provenance section and the real checker content, without raising
on a tree where a file is missing.

ISOLATED FROM THE LIVE ARTIFACT (fixed 2026-10-21, issue #213 / event #213): these tests used to
call `w.main(...)` with the script's real output directory in effect, so every run OVERWROTE the
committed docs/evidence/briefings/closure-note-2026-10-10.md (and created a stray
closure-note-1999-12-31.md in the same tracked directory, deleted only in a `finally`). The output
dir is now redirected to a temp directory per test, the assertions moved with it, and each test
asserts the COMMITTED file's mtime is unchanged — the isolation is verified, not assumed. Coverage
is unchanged: the note is still produced and still asserted on.

stdlib-only (unittest).

Run: python3 tests/test_write_closure_note.py
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "write_closure_note.py"
COMMITTED_DIR = REPO / "docs" / "evidence" / "briefings"

_spec = importlib.util.spec_from_file_location("write_closure_note", SCRIPT)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)  # pylint: disable=protected-access


class TestSh(unittest.TestCase):
    def test_captures_output(self):
        self.assertIn("provenance", w.sh("echo", "provenance"))


class _IsolatedMain(unittest.TestCase):
    """Base: run main() with its output dir pointed at a temp dir, and prove the live
    artifact was not touched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="write-closure-note-")
        self.evid = Path(self._tmp.name)
        self._live = COMMITTED_DIR / "closure-note-2026-10-10.md"
        self._live_before = (self._live.exists(),
                             self._live.stat().st_mtime_ns if self._live.exists() else None)
        self._live_dir_before = sorted(p.name for p in COMMITTED_DIR.glob("closure-note-*"))

    def tearDown(self):
        self._tmp.cleanup()
        after = (self._live.exists(),
                 self._live.stat().st_mtime_ns if self._live.exists() else None)
        self.assertEqual(
            after, self._live_before,
            f"the run modified the COMMITTED artifact {self._live} — the test is writing "
            "live evidence again (issue #213)")
        self.assertEqual(
            sorted(p.name for p in COMMITTED_DIR.glob("closure-note-*")), self._live_dir_before,
            "the run created or removed a file in the tracked evidence directory")


class TestMain(_IsolatedMain):
    def test_writes_note_with_provenance_and_checker_output(self):
        code = w.main("2026-10-10", out_dir=self.evid)
        self.assertEqual(code, 0)
        dest = self.evid / "closure-note-2026-10-10.md"
        self.assertTrue(dest.exists())
        text = dest.read_text(encoding="utf-8")
        self.assertIn("## A. The 'file both added and modified' finding", text)
        self.assertIn("git log --oneline --follow", text)
        # The checker verdict must appear as real captured output.
        self.assertIn("RESULT: ALL PASS", text)
        # And the test-body assertions the reviewer asked to see.
        self.assertIn("test_pdf_written_non_trivial", text)
        self.assertIn("%PDF", text)

    def test_does_not_raise_when_artifacts_absent(self):
        # A date with no artifacts must still produce a note (empty sections),
        # never crash.
        code = w.main("1999-12-31", out_dir=self.evid)
        dest = self.evid / "closure-note-1999-12-31.md"
        self.assertEqual(code, 0)
        self.assertTrue(dest.exists())


class TestDefaultDestinationUnchanged(unittest.TestCase):
    """Production behaviour must not move: with no out_dir argument the note still goes to the
    real briefings dir."""

    def test_out_evid_defaults_to_evid(self):
        self.assertEqual(w.OUT_EVID, w.EVID)

    def test_main_accepts_an_out_dir_parameter(self):
        import inspect
        params = inspect.signature(w.main).parameters
        self.assertIn("out_dir", params, "main() must expose the redirect parameter")
        self.assertIsNone(params["out_dir"].default)


if __name__ == "__main__":
    unittest.main()
