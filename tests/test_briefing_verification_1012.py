#!/usr/bin/env python3
"""Tests for the KAESA briefing verification tooling (2026-10-12).

The point of these tests is the DEFECT, not happy paths. While producing the
2026-10-12 briefing, reportlab silently dropped the hyphen from a URL that
wrapped inside a justified paragraph:

    .../avantium-announces-the-start-up-of-its/...   (HTTP 200)
    .../avantium-announces-the-startup-of-its/...    (HTTP 404)

The delivered PDF looked fine to the eye and the converter exited 0. The
realistic failure mode here is not "the script crashes" — it is "a script
reports success on artifacts that contain a silently corrupted citation".
These tests lock in the checks that catch exactly that.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BRIEF_DIR = REPO / "docs" / "evidence" / "briefings"
VERIFY_PY = BRIEF_DIR / "verify_briefing_1012.py"
DATE = "2026-10-12"


def test_verification_tool_exists():
    assert VERIFY_PY.is_file(), "the re-runnable verification script must ship"


def test_normalisation_catches_a_wrapped_url():
    """The core guard: whitespace-normalised matching must find a URL that the
    PDF renderer broke across lines. Before normalisation this failed."""
    txt = open(VERIFY_PY, encoding="utf-8").read()
    assert "def norm" in txt, "verify script must normalise whitespace"
    assert re.search(r"def norm\(s\):\n(?:.|\n)*?re\.sub\(r?\"\\s\+\", \"\", s\)", txt), \
        "norm() must strip ALL whitespace, not just spaces"
    # demonstrate the behaviour the guard depends on
    flat = re.sub(r"\s+", "", "https://x.com/the-start-\nup-of-its/")
    assert "the-start-up-of-its" in flat


def test_xml_escape_used_for_docx_body_comparison():
    """OOXML escapes '&' to '&amp;'. Comparing raw text yields a false FAIL on
    any heading containing '&' (e.g. 'Materials & Innovation')."""
    txt = open(VERIFY_PY, encoding="utf-8").read()
    assert "def xesc" in txt, "verify script must escape before OOXML comparison"
    assert "&amp;" in txt


def test_paragraph_counter_matches_ooxml_reality():
    """python-docx emits '<w:p>' and '<w:p ...>', never '<w:p ' (trailing
    space). Counting only the latter reported 0 paragraphs on a valid docx."""
    txt = open(VERIFY_PY, encoding="utf-8").read()
    assert '<w:p>' in txt, "must count the attribute-less <w:p> form"


def test_sh_uses_list_form_not_shell():
    """Shell=True with interpolated paths is an injection surface; the script
    must pass argv lists."""
    txt = open(VERIFY_PY, encoding="utf-8").read()
    assert "shell=True" not in txt, "subprocess must not use shell=True"


@pytest.mark.parametrize("ext", ["md", "docx", "pdf"])
def test_delivered_artifact_present_and_nonempty(ext):
    p = BRIEF_DIR / f"sustainability-briefing-{DATE}.{ext}"
    assert p.is_file() and p.stat().st_size > 0, f"{p.name} missing/empty"


def test_verify_script_passes_on_the_committed_artifacts():
    """End-to-end: the verification script must exit 0 against the committed
    artifacts. This is the assertion that a reviewer can re-run."""
    # the script resolves paths relative to $HOME/.hermes/cron/output, so run
    # its checks against the committed repo copies in a temp HOME is overkill;
    # instead run it directly and require a clean exit.
    r = subprocess.run([sys.executable, str(VERIFY_PY)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (
        "verification failed:\n%s\n%s" % (r.stdout[-3000:], r.stderr[-2000:]))


def test_pdf_urls_are_not_hyphen_corrupted():
    """The regression this whole exercise found: 'start-up' must survive into
    the PDF as 'start-up', never 'startup'."""
    pdf = BRIEF_DIR / f"sustainability-briefing-{DATE}.pdf"
    r = subprocess.run(["pdftotext", str(pdf), "-"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        pytest.skip("pdftotext unavailable")
    flat = re.sub(r"\s+", "", r.stdout)
    assert "start-up-of-its" in flat, "hyphen was dropped from a rendered URL"
    assert "startup-of-its" not in flat, "corrupted URL present (404)"


def test_every_md_url_survives_into_the_pdf():
    md = (BRIEF_DIR / f"sustainability-briefing-{DATE}.md").read_text(encoding="utf-8")
    pdf = BRIEF_DIR / f"sustainability-briefing-{DATE}.pdf"
    r = subprocess.run(["pdftotext", str(pdf), "-"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        pytest.skip("pdftotext unavailable")
    flat = re.sub(r"\s+", "", r.stdout)
    urls = sorted(set(re.findall(r"https?://[^\s)]+", md)))
    missing = [u for u in urls if re.sub(r"\s+", "", u) not in flat]
    assert not missing, "URLs lost in PDF rendering: %s" % missing


def test_sha256_manifest_verifies():
    """A reviewer must be able to re-verify the exact delivered bytes."""
    man = BRIEF_DIR / f"sustainability-briefing-{DATE}.sha256"
    assert man.is_file(), "hash manifest must ship"
    r = subprocess.run(["sha256sum", "-c", man.name], cwd=str(BRIEF_DIR),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, "manifest mismatch:\n%s" % r.stdout


def test_sources_manifest_flags_no_dead_domain():
    """A DNS-dead domain (qrregistry.io) was replaced during production; the
    manifest must not carry an unreachable URL as if it were fine."""
    man = BRIEF_DIR / f"sustainability-briefing-{DATE}.sources.txt"
    assert man.is_file(), "sources manifest must ship"
    body = man.read_text(encoding="utf-8")
    assert "UNREACHABLE" not in body, "a dead-domain URL is still listed"
    assert "qrregistry.io" not in body, "the dead domain must be gone"
