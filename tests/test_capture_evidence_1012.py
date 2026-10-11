#!/usr/bin/env python3
"""Tests for the briefing evidence-capture tooling (capture_evidence_1012.py).

The realistic failure for an evidence generator is not "it crashes" — it is
"it writes a file that LOOKS like evidence but contains no captured output",
which is exactly the self-adversarial finding this script answers. These
tests assert the evidence files carry real command output, a real exit code,
and a real claim->source mapping.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EVID = REPO / "docs" / "evidence" / "briefings"
CAPTURE = EVID / "capture_evidence_1012.py"
DATE = "2026-10-12"

EVIDENCE_FILES = [
    EVID / ("verification-%s.txt" % DATE),
    EVID / ("test-results-%s.txt" % DATE),
    EVID / ("url-check-%s.txt" % DATE),
]
CLAIM_TSV = EVID / ("claim-sources-%s.tsv" % DATE)


def test_capture_tool_exists():
    assert CAPTURE.is_file(), "the evidence generator must ship with its output"


@pytest.mark.parametrize("path", EVIDENCE_FILES)
def test_evidence_file_records_command_and_exit_code(path):
    """Captured evidence is only re-executable if it names what was run and
    what it returned."""
    assert path.is_file(), "%s missing" % path.name
    t = path.read_text(encoding="utf-8")
    assert "command:" in t, "%s does not record the command" % path.name
    assert re.search(r"exit code: \d+", t), \
        "%s does not record an exit code" % path.name


@pytest.mark.parametrize("path", EVIDENCE_FILES)
def test_evidence_file_contains_real_captured_output(path):
    """Guard against the failure mode this whole exercise targets: a file
    that is framework prose with no actual program output in it."""
    t = path.read_text(encoding="utf-8")
    # the real tools emit PASS/FAIL lines or an HTTP code inventory
    assert re.search(r"^(PASS|FAIL)\s", t, re.M) or "http" in t, \
        "%s has no captured PASS/FAIL or HTTP output" % path.name
    assert t.count("\n") > 10, "%s is too short to hold real output" % path.name


def test_test_results_evidence_reports_zero_failures():
    t = (EVID / ("test-results-%s.txt" % DATE)).read_text(encoding="utf-8")
    m = re.search(r"ran=(\d+) passed=(\d+) failed=(\d+)", t)
    assert m, "test-results evidence lacks a ran/passed/failed summary"
    ran, passed, failed = (int(g) for g in m.groups())
    assert failed == 0, "committed test evidence records failures"
    assert passed == ran and ran >= 13, \
        "expected >=13 passing tests, got ran=%d passed=%d" % (ran, passed)


def test_url_evidence_keeps_both_md_and_pdf_inventory():
    t = (EVID / ("url-check-%s.txt" % DATE)).read_text(encoding="utf-8")
    assert "distinct URLs in .md" in t and "distinct URLs in .pdf" in t, \
        "url evidence must show both inventories so a PDF-only loss is visible"
    assert re.search(r"in \.md but NOT in \.pdf:\s*0", t), \
        "a URL present in the .md is missing from the .pdf"


def test_claim_source_map_is_machine_readable_and_complete():
    assert CLAIM_TSV.is_file(), "claim -> source map must ship"
    rows = [ln for ln in CLAIM_TSV.read_text(encoding="utf-8").split("\n")
            if ln and not ln.startswith("#")]
    assert rows[0].split("\t") == ["claim_anchor", "source_url"], \
        "TSV header must be claim_anchor<TAB>source_url"
    body = rows[1:]
    assert len(body) >= 15, "expected >=15 claim/source rows, got %d" % len(body)
    for r in body:
        parts = r.split("\t")
        assert len(parts) == 2, "row is not two tab-separated fields: %r" % r
        claim, url = parts
        assert claim.strip(), "empty claim anchor"
        assert url.startswith("https://"), "non-absolute source: %r" % url


def test_claim_source_map_covers_every_md_url():
    """Every source URL in the briefing must appear in the map, or the map is
    a partial picture presented as complete."""
    md = (EVID / ("sustainability-briefing-%s.md" % DATE)).read_text(encoding="utf-8")
    md_urls = set(re.findall(r"https?://[^\s)]+", md))
    with open(CLAIM_TSV, encoding="utf-8") as fh:
        mapped = {ln.split("\t")[1].strip() for ln in fh
                  if ln.strip() and not ln.startswith("#")
                  and "\t" in ln and ln.split("\t")[1].strip().startswith("http")}
    missing = md_urls - mapped
    assert not missing, "URLs in the briefing are absent from the map: %s" % missing


def test_capture_tool_has_no_hardcoded_home_path():
    t = CAPTURE.read_text(encoding="utf-8")
    assert not re.search(r"/home/\w+/", t), \
        "evidence tool must use ~/Path.home(), not a literal home path"


@pytest.mark.parametrize("path", EVIDENCE_FILES + [CLAIM_TSV])
def test_committed_evidence_is_path_neutral(path):
    """Host-specific absolute paths are noise in a shared repo and trip the
    secret-leak detector; the capture tool must sanitise them.

    Matches a REAL home path (a literal username segment), not the escaped
    regex text `\\/home\\/\\\\w+\\/` that appears when a test's own source is
    echoed into captured output.
    """
    assert path.is_file(), "%s missing" % path.name
    t = path.read_text(encoding="utf-8")
    real = re.findall(r"/home/(?!\\w\+/|\\\\w)[a-z][a-z0-9_-]+/", t)
    assert not real, "%s embeds absolute home paths: %s" % (path.name, real)


TOOLING = [
    EVID / "check_urls_1012.py",
    EVID / "make_src_1012.py",
    EVID / "make_briefing_files_1012.py",
    EVID / "capture_evidence_1012.py",
    EVID / "manifest_1012.py",
    EVID / "sources_manifest_1012.py",
    EVID / "verify_briefing_1012.py",
]


@pytest.mark.parametrize("path", TOOLING)
def test_tooling_is_path_neutral(path):
    """Regression guard. A manifest run once copied the cron-output copies of
    these scripts back over the repo's fixed ones, silently reinstating
    /home/<user> literals in committed evidence. Assert it cannot recur."""
    assert path.is_file(), "%s missing" % path.name
    t = path.read_text(encoding="utf-8")
    real = re.findall(r"/home/(?!\\w\+/|\\\\w)[a-z][a-z0-9_-]+/", t)
    assert not real, "%s embeds absolute home paths: %s" % (path.name, real)


def test_committed_evidence_records_no_failures():
    """A committed evidence file that contains a failing test would be
    self-contradicting. Guard the whole set, not just the summary line."""
    for path in EVIDENCE_FILES:
        t = path.read_text(encoding="utf-8")
        assert "VERDICT: FAIL" not in t, \
            "%s records a FAIL verdict" % path.name
        assert not re.search(r"^FAIL\s", t, re.M), \
            "%s contains a FAIL line" % path.name


DELIVERY_CHECK = EVID / ("delivery-path-check-%s.txt" % DATE)
DELIVERY_SCRIPT = EVID / "verify_delivery_path_1012.py"


def test_delivery_check_script_and_output_ship():
    """The required output path is outside the repo, so the repo diff cannot
    show the deliverables exist there. Commit both the check and its output."""
    assert DELIVERY_SCRIPT.is_file(), "delivery-path check must ship"
    assert DELIVERY_CHECK.is_file(), "delivery-path check output must ship"


def test_delivery_check_output_reports_verified():
    t = DELIVERY_CHECK.read_text(encoding="utf-8")
    assert "RESULT: ALL DELIVERABLES VERIFIED" in t, \
        "committed delivery-path output does not report success"
    for ext in ("md", "docx", "pdf"):
        assert "byte-identical to repo copy" in t, \
            "no byte-identity assertion recorded for %s" % ext
        assert re.search(r"^%s\s+\d+" % ext, t, re.M), \
            "no size recorded for %s" % ext
    assert not re.search(r"MISSING AT DELIVERY PATH|DIFFERS FROM REPO COPY", t), \
        "committed delivery-path output records a failure"


def test_delivery_check_output_is_path_neutral():
    """Committed evidence must not embed host-specific absolute paths."""
    t = DELIVERY_CHECK.read_text(encoding="utf-8")
    real = re.findall(r"/home/(?!\\w\+/|\\\\w)[a-z][a-z0-9_-]+/", t)
    assert not real, "delivery-path output embeds home paths: %s" % real


EMBED_SCRIPT = EVID / "embed_evidence_1012.py"
NOTE = EVID / ("closure-note-%s.md" % DATE)
APPENDIX_MARKER = "## Appendix — verbatim committed evidence"


def test_embed_tool_ships():
    assert EMBED_SCRIPT.is_file(), "evidence-embedding tool must ship"


def test_closure_note_contains_verbatim_evidence_appendix():
    """The review material is the diff; the diff must therefore carry the
    evidence content, not a pointer to it."""
    assert NOTE.is_file(), "closure note must ship"
    t = NOTE.read_text(encoding="utf-8")
    assert APPENDIX_MARKER in t, "closure note lacks the evidence appendix"
    for name in ("verification-%s.txt" % DATE,
                 "test-results-%s.txt" % DATE,
                 "url-check-%s.txt" % DATE,
                 "delivery-path-check-%s.txt" % DATE,
                 "claim-sources-%s.tsv" % DATE):
        assert "### `%s`" % name in t, "appendix omits %s" % name


def test_appendix_blocks_are_non_trivial():
    """An empty fenced block would satisfy the marker check while carrying no
    evidence. Require real content between the fences."""
    t = NOTE.read_text(encoding="utf-8")
    blocks = re.findall(r"```\n(.*?)\n```", t, re.S)
    assert len(blocks) >= 5, "expected >=5 fenced evidence blocks"
    for b in blocks:
        assert len(b.strip()) > 200, \
            "an evidence block is suspiciously short (%d chars)" % len(b.strip())
    joined = "\n".join(blocks)
    assert "RESULT: ALL CHECKS PASSED" in joined
    assert "RESULT: ALL TESTS PASSED" in joined
    assert "RESULT: ALL DELIVERABLES VERIFIED" in joined


def test_embed_is_idempotent():
    """Re-running the embedder must not stack duplicate appendices (the tool
    is invoked repeatedly during a run)."""
    t = NOTE.read_text(encoding="utf-8")
    assert t.count(APPENDIX_MARKER) == 1, \
        "appendix marker appears %d times" % t.count(APPENDIX_MARKER)
