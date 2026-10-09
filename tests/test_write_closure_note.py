"""Tests for ops/scripts/sustainability/write_closure_note.py.

The note exists to answer reviewer findings with git facts. The test asserts
it emits the provenance section and the real checker content, without raising
on a tree where a file is missing.

stdlib-only (unittest).

Run: python3 tests/test_write_closure_note.py
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "write_closure_note.py"

_spec = importlib.util.spec_from_file_location("write_closure_note", SCRIPT)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)  # pylint: disable=protected-access


class TestSh(unittest.TestCase):
    def test_captures_output(self):
        self.assertIn("provenance", w.sh("echo", "provenance"))


class TestMain(unittest.TestCase):
    def test_writes_note_with_provenance_and_checker_output(self):
        code = w.main("2026-10-10")
        self.assertEqual(code, 0)
        dest = REPO / "docs" / "evidence" / "briefings" / (
            "closure-note-2026-10-10.md")
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
        code = w.main("1999-12-31")
        dest = REPO / "docs" / "evidence" / "briefings" / (
            "closure-note-1999-12-31.md")
        try:
            self.assertEqual(code, 0)
            self.assertTrue(dest.exists())
        finally:
            dest.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
