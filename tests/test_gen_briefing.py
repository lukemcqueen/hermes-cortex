"""Tests for ops/scripts/sustainability/gen_briefing.py.

stdlib-only (unittest) like test_verify_briefing.py: the cron host's venv has
python-docx/reportlab but the *repo* interpreter may not, so the parsing layer
(the part that can silently corrupt content) is tested without those deps.
The docx/pdf build paths are exercised only when the libs import, and skipped
otherwise rather than faked.

Run: python3 tests/test_gen_briefing.py
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "gen_briefing.py"

_spec = importlib.util.spec_from_file_location("gen_briefing", SCRIPT)
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)  # pylint: disable=protected-access


class TestParseMd(unittest.TestCase):
    def test_classifies_block_kinds(self):
        md = ("# Title\n\n## Section\n\n- bullet one\n\nplain para\n\n---\n")
        kinds = [k for k, _ in g.parse_md(md)]
        self.assertEqual(kinds, ["h1", "h2", "bullet", "para", "rule"])

    def test_strips_heading_markers(self):
        blocks = dict(g.parse_md("# Big\n## Small\n"))
        self.assertEqual(blocks["h1"], "Big")
        self.assertEqual(blocks["h2"], "Small")

    def test_bullet_marker_removed(self):
        [(kind, payload)] = list(g.parse_md("- **Item** — text\n"))
        self.assertEqual(kind, "bullet")
        self.assertFalse(payload.startswith("-"))
        self.assertIn("**Item**", payload)

    def test_blank_lines_ignored(self):
        self.assertEqual(list(g.parse_md("\n\n\n")), [])


class TestInlineRuns(unittest.TestCase):
    def test_bold_detected(self):
        runs = g.inline_runs("plain **bold** tail")
        self.assertEqual(runs, [("plain", False), ("bold", True), ("tail", False)])

    def test_no_bold_is_single_run(self):
        self.assertEqual(g.inline_runs("all plain"), [("all plain", False)])

    def test_empty_input_yields_placeholder(self):
        self.assertEqual(g.inline_runs(""), [("", False)])


class TestLinkify(unittest.TestCase):
    def test_markdown_link_becomes_readable(self):
        out = g.linkify("see [EU law](https://example.com/x)")
        self.assertEqual(out, "see EU law (https://example.com/x)")

    def test_non_link_text_untouched(self):
        self.assertEqual(g.linkify("no links here"), "no links here")


class TestBuilders(unittest.TestCase):
    """Build paths run only when the render libs are importable."""

    def _blocks(self):
        return list(g.parse_md(
            "# Sustainable Materials & Market Intelligence Briefing\n\n"
            "## Saturday, 10 October 2026 — prepared for Amy, KAESA\n\n"
            "## 1. Headline\n\nBody text with **bold**.\n"
            "Source: https://example.com/x\n\n"
            "## 2. Materials & Innovation\n\n- item one\n"
            "Source: https://example.com/y\n\n"
            "## 3. Policy & Regulation\n\n- item two\n"
            "Source: https://example.com/z\n\n"
            "## 4. Market Intelligence\n\n- item three\n"
            "Source: https://example.com/w\n\n"
            "## 5. For Your Radar\n\n- item four\n"
            "Source: https://example.com/v\n"
        ))

    def test_docx_carries_markers(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx not installed")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "b.docx"
            g.build_docx(self._blocks(), str(out))
            self.assertTrue(out.exists() and out.stat().st_size > 2000)
            text = "\n".join(p.text for p in Document(str(out)).paragraphs)
            for marker in ("Amy", "KAESA", "2026"):
                self.assertIn(marker, text, f"marker missing from docx: {marker}")

    def test_pdf_written_non_trivial(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab not installed")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "b.pdf"
            g.build_pdf(self._blocks(), str(out))
            self.assertTrue(out.exists() and out.stat().st_size > 1000)
            self.assertEqual(out.read_bytes()[:4], b"%PDF")

    def test_main_fails_on_missing_md(self):
        with tempfile.TemporaryDirectory() as td:
            orig = g.OUT
            g.OUT = td
            try:
                self.assertEqual(g.main("1999-01-01"), 1)
            finally:
                g.OUT = orig


if __name__ == "__main__":
    unittest.main()
