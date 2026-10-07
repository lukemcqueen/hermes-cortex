"""Tests for ops/scripts/sustainability/verify_briefing.py.

stdlib-only (unittest) on purpose: pytest is NOT installed in the cron host's
venv, so a pytest test would be unrunnable exactly where the checker runs. This
module executes with `python3 tests/test_verify_briefing.py` and also under
`python3 -m unittest discover`. The repo's pytest config collects it too (test_*
naming), so CI sees it either way.

Assertions include the negatives that matter: the checker must FAIL on real
defects (over-long, too-short, malformed Source line, missing radar heading,
missing file) — not merely print PASS.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "verify_briefing.py"

_spec = importlib.util.spec_from_file_location("verify_briefing", SCRIPT)
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)  # pylint: disable=protected-access

GOOD_MD = """# Sustainable Materials & Market Intelligence Briefing

**Thursday, 8 October 2026 - Prepared for Amy, CEO - KAESA**

---

## 1. Materials & Innovation

Something specific about materials with a number like 40%.
Source: https://example.com/materials

## 2. Policy & Regulation

A rule change with a date.
Source: https://example.com/policy

## 3. Market Intelligence

A market figure.
Source: https://example.com/market

## 4. For Your Radar

A curated item.
Source: https://example.com/radar
""" + "".join(f"\nSource: https://example.com/extra-{i}" for i in range(9)) + "\n" + (" word" * 700)


class TestChecks(unittest.TestCase):
    def test_sections_good(self):
        self.assertTrue(v.check_sections(GOOD_MD))

    def test_sections_reject_missing_radar(self):
        bad = GOOD_MD.replace("## 4. For Your Radar", "## 4. Something Else")
        self.assertFalse(v.check_sections(bad))

    def test_sources_good(self):
        self.assertTrue(v.check_sources(GOOD_MD))

    def test_sources_reject_malformed_line(self):
        bad = GOOD_MD.replace("Source: https://example.com/policy",
                              "Source: not-a-url")
        self.assertFalse(v.check_sources(bad))

    def test_words_good(self):
        self.assertTrue(v.check_word_count(GOOD_MD))

    def test_words_reject_too_long(self):
        self.assertFalse(v.check_word_count(GOOD_MD + " word " * 900))

    def test_words_reject_too_short(self):
        self.assertFalse(v.check_word_count("# tiny\n\n## 1. x\n"))

    def test_files_good(self):
        # exercises the FILE path: build the full .md/.docx/.pdf triple.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "sustainability-briefing-2026-10-08"
            (base.with_suffix(".md")).write_text(GOOD_MD)
            (base.with_suffix(".docx")).write_bytes(b"x" * 2000)
            (base.with_suffix(".pdf")).write_bytes(b"x" * 2000)
            self.assertTrue(v.check_files(td, "2026-10-08"))

    def test_files_reject_missing_binary(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "sustainability-briefing-2026-10-08"
            (base.with_suffix(".md")).write_text(GOOD_MD)  # docx/pdf absent
            self.assertFalse(v.check_files(td, "2026-10-08"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
