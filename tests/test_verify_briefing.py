"""Tests for ops/scripts/sustainability/verify_briefing.py.

Iron Law: written BEFORE the production script. These import the module under
test and assert the checker's behaviour on synthetic inputs — a passing
briefing, a too-long briefing, a malformed source line, and a missing file.

The checker validates the daily sustainability briefing artifacts written by
the content-production cron. It must FAIL on real defects, not just print PASS.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "verify_briefing.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_briefing", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GOOD_MD = """# Sustainable Materials & Market Intelligence Briefing

**Thursday, 8 October 2026 · Prepared for Amy, CEO — KAESA**

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
""" + (" word" * 700)


def _make_bundle(tmp_path: Path, md_text: str):
    (tmp_path / "sustainability-briefing-2026-10-08.md").write_text(md_text)
    # non-trivial stand-ins; the binary-content checks are exercised in the
    # integration run against the real artifacts, not here.
    (tmp_path / "sustainability-briefing-2026-10-08.docx").write_bytes(b"x" * 2000)
    (tmp_path / "sustainability-briefing-2026-10-08.pdf").write_bytes(b"x" * 2000)
    return tmp_path


def test_good_briefing_passes(tmp_path):
    v = _load()
    _make_bundle(tmp_path, GOOD_MD)
    assert v.check_sections(GOOD_MD) is True
    assert v.check_sources(GOOD_MD) is True
    assert v.check_word_count(GOOD_MD) is True


def test_word_count_rejects_over_long():
    v = _load()
    long_md = GOOD_MD + (" word " * 900)  # pushes well past 1200
    assert v.check_word_count(long_md) is False


def test_word_count_rejects_too_short():
    v = _load()
    assert v.check_word_count("# tiny\n\n## 1. x\n") is False


def test_sources_reject_malformed_line():
    v = _load()
    bad = GOOD_MD.replace("Source: https://example.com/policy",
                          "Source: not-a-url")
    assert v.check_sources(bad) is False


def test_sections_reject_missing_radar():
    v = _load()
    bad = GOOD_MD.replace("## 4. For Your Radar", "## 4. Something Else")
    assert v.check_sections(bad) is False


def test_missing_file_fails(tmp_path):
    v = _load()
    (tmp_path / "sustainability-briefing-2026-10-08.md").write_text(GOOD_MD)
    # docx/pdf absent
    assert v.check_files(tmp_path, "2026-10-08") is False
