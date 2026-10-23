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
import re
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


REAL_DIR = REPO / "docs" / "evidence" / "sustainability-briefing-2026-10-08"
REAL_DATE = "2026-10-08"


def _write_docx(path: Path, text: str) -> None:
    """Minimal .docx the checker's extractor can read (zip + document.xml)."""
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml",
                   f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>")


# A briefing about a DIFFERENT subject than the EU green-claims directive: it
# must still pass a check whose job is "do the binaries carry the briefing
# text". The topic word ('EmpCo') appears nowhere in it.
TOPICAL_MD = """# Sustainable Materials & Market Intelligence Briefing

**Thursday, 22 October 2026** — prepared for Amy, KAESA

## 1. The headline: Korea's greenwashing rulebook got teeth

Seoul moved from warnings to structure, with a substantiation regime.
Source: https://example.com/korea

## 2. Materials & Innovation

Mushroom leather cleared a durability bar in Fashion and Textiles.
Source: https://example.com/mushroom

## 3. Policy & Regulation

The destruction ban is live for large enterprises.
Source: https://example.com/espr

## 4. Market Intelligence

The luxury handbag market grows on leather.
Source: https://example.com/handbag

## For Your Radar

Watch the textile delegated act timing.
Source: https://example.com/radar
"""


class TestBinaryCarryText(unittest.TestCase):
    """check_binary_carry_text must bind to THIS briefing's text.

    Measured 2026-10-23: the check demanded the literal topic word 'EmpCo',
    so a healthy briefing on any other subject failed a check whose contract
    is about the .docx/.pdf carrying the briefing — a false positive that
    fires on correct work.
    """

    def setUp(self):
        self._real_docx = v._docx_text
        self._real_pdf = v._pdf_text
        self._td = tempfile.TemporaryDirectory()
        self.dir = self._td.name
        self.date = "2026-10-22"
        self.base = Path(self.dir) / f"sustainability-briefing-{self.date}"
        self.base.with_suffix(".md").write_text(TOPICAL_MD)

    def tearDown(self):
        v._docx_text = self._real_docx
        v._pdf_text = self._real_pdf
        self._td.cleanup()

    def _stub_binaries(self, docx_text: str, pdf_text: str) -> None:
        _write_docx(self.base.with_suffix(".docx"), docx_text)
        v._pdf_text = lambda p: pdf_text

    def test_topical_briefing_carrying_its_text_passes(self):
        # The regression pin: no fixed topic token exists in this briefing.
        plain = re.sub(r"[*#]", "", TOPICAL_MD)
        self._stub_binaries(plain, plain)
        self.assertTrue(v.check_binary_carry_text(self.dir, self.date))

    def test_docx_with_unrelated_text_fails(self):
        self._stub_binaries("Annual Report 2019 — total revenue", TOPICAL_MD)
        self.assertFalse(v.check_binary_carry_text(self.dir, self.date))

    def test_empty_pdf_fails(self):
        # pdftotext absent or a scanned/garbled pdf yields no text.
        self._stub_binaries(TOPICAL_MD, "")
        self.assertFalse(v.check_binary_carry_text(self.dir, self.date))

    def test_docx_carrying_only_the_title_fails(self):
        self._stub_binaries(
            "Sustainable Materials & Market Intelligence Briefing", TOPICAL_MD)
        self.assertFalse(v.check_binary_carry_text(self.dir, self.date))


class TestRealArtifacts(unittest.TestCase):
    """Run the checker against the ACTUAL delivered artifacts, not fakes.

    Skipped (not failed) if the evidence bundle is absent, so the suite still
    runs on a checkout that does not carry cron evidence.
    """

    def setUp(self):
        if not (REAL_DIR / f"sustainability-briefing-{REAL_DATE}.md").exists():
            self.skipTest("evidence bundle not present in this checkout")

    def test_delivered_files_present(self):
        self.assertTrue(v.check_files(str(REAL_DIR), REAL_DATE))

    def test_delivered_sections(self):
        text = (REAL_DIR / f"sustainability-briefing-{REAL_DATE}.md").read_text()
        self.assertTrue(v.check_sections(text))

    def test_delivered_sources(self):
        text = (REAL_DIR / f"sustainability-briefing-{REAL_DATE}.md").read_text()
        self.assertTrue(v.check_sources(text))

    def test_delivered_word_count(self):
        text = (REAL_DIR / f"sustainability-briefing-{REAL_DATE}.md").read_text()
        self.assertTrue(v.check_word_count(text))

    def test_delivered_binaries_carry_text(self):
        # the REAL committed .docx/.pdf, via the same extractor the CLI uses
        self.assertTrue(v.check_binary_carry_text(str(REAL_DIR), REAL_DATE))

    def test_delivered_sources_resolve_to_known_domains(self):
        # Provenance check: every Source: URL must be well-formed AND its host
        # must be in the allowlist of sources actually returned by this
        # session's web_search calls. This is the reproducible, committed form of
        # the provenance claim (source-to-call correspondence itself is not
        # reproducible, but URL well-formedness + expected-host membership is).
        import urllib.parse
        text = (REAL_DIR / f"sustainability-briefing-{REAL_DATE}.md").read_text()
        urls = re.findall(r"^Source: (https?://\S+)$", text, re.M)
        self.assertEqual(len(urls), 16)  # exact count claimed in the briefing
        allowed = {
            "www.vogue.com", "vegconomist.com", "www.acs.org",
            "sustainablefutures.linklaters.com", "www.bluesign.com",
            "single-market-economy.ec.europa.eu", "wetrack.fashion",
            "www.fsc.go.kr", "www.asiae.co.kr", "www.bcg.com",
            "www.mcleukerai.com", "pmarketresearch.com", "www.nature.org",
            "innovationintextiles.com", "infashionbusiness.com",
        }
        hosts = {urllib.parse.urlparse(u).netloc for u in urls}
        unknown = hosts - allowed
        self.assertEqual(unknown, set(),
                         f"source host(s) not in the session allowlist: {unknown}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
