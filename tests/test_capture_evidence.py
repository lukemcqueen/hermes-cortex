"""Tests for ops/scripts/sustainability/capture_evidence.py.

stdlib-only (unittest). The point of this script is that its evidence file is
RE-RUNNABLE: it must record the checker's real stdout/exit code and the real
sha256 of each artifact, and it must not claim success when an artifact is
missing. These tests assert both the positive and the negative.

Run: python3 tests/test_capture_evidence.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "capture_evidence.py"

_spec = importlib.util.spec_from_file_location("capture_evidence", SCRIPT)
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)  # pylint: disable=protected-access


class TestSha256(unittest.TestCase):
    def test_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.bin"
            p.write_bytes(b"hello world")
            expected = hashlib.sha256(b"hello world").hexdigest()
            self.assertEqual(c.sha256(str(p)), expected)


class TestMain(unittest.TestCase):
    def _seed(self, td: Path, date: str, *, with_sources: bool = True):
        base = td / f"sustainability-briefing-{date}"
        body = (
            "# Sustainable Materials & Market Intelligence Briefing\n"
            "## Saturday, 10 October 2026 — prepared for Amy, KAESA\n\n"
            "## 1. Headline\n\n" + "word " * 700 + "\n"
        )
        if with_sources:
            body += "".join(
                f"Source: https://example.com/s{i}\n" for i in range(14))
        base.with_suffix(".md").write_text(body, encoding="utf-8")
        base.with_suffix(".docx").write_bytes(b"x" * 4000)
        base.with_suffix(".pdf").write_bytes(b"x" * 4000)
        return base

    def test_writes_evidence_file(self):
        with tempfile.TemporaryDirectory() as td:
            orig = c.OUT
            c.OUT = td
            try:
                self._seed(Path(td), "2030-01-01")
                self.assertEqual(c.main("2030-01-01"), 0)
                out = Path(td) / "verification-2030-01-01.txt"
                self.assertTrue(out.exists())
                text = out.read_text(encoding="utf-8")
                self.assertIn("checker_exit=", text)
                self.assertIn("--- artifact listing + sha256", text)
                self.assertIn("Source: lines: 14", text)
            finally:
                c.OUT = orig

    def test_records_missing_artifact_not_silent(self):
        with tempfile.TemporaryDirectory() as td:
            orig = c.OUT
            c.OUT = td
            try:
                base = self._seed(Path(td), "2030-01-02")
                base.with_suffix(".pdf").unlink()  # deliberately remove one
                c.main("2030-01-02")
                text = (Path(td) / "verification-2030-01-02.txt").read_text(
                    encoding="utf-8")
                self.assertIn("MISSING", text)
            finally:
                c.OUT = orig

    def test_missing_md_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as td:
            orig = c.OUT
            c.OUT = td
            try:
                # no artifacts seeded at all
                self.assertEqual(c.main("2030-01-03"), 0)
                text = (Path(td) / "verification-2030-01-03.txt").read_text(
                    encoding="utf-8")
                self.assertIn("MISSING", text)
            finally:
                c.OUT = orig


if __name__ == "__main__":
    unittest.main()
