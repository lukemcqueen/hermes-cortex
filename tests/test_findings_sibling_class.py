#!/usr/bin/env python3
"""A finding aimed at ANOTHER file of the same range does not block the file under review.

The per-blob window shows one file plus the range's sibling paths. A reviewer that cannot see a
sibling's content files an `unverified-claim` against the file it CAN see, and its own recommendation
often says so ("no change to THIS file is required; the resolution belongs to the sibling's own
review"). Blocking on that refuses a close that no edit to the judged file can clear.

The classifier is keyed STRUCTURALLY — technique, the paths named in `target`, and the range's
sibling list — never on the wording of a recommendation, so a real behavioural defect phrased as
"the fix belongs elsewhere" still blocks.

Boundary this file asserts:
  A. unverified-claim whose target names a sibling and NOT the reviewed path -> annotating, not blocking;
  B. the same finding whose target ALSO names the reviewed path -> blocking (the reviewed file wins);
  C. technique other than unverified-claim -> blocking, sibling target or not;
  D. a prose target (no path) -> blocking;
  E. no sibling context supplied -> blocking (absent context never downgrades);
  F. unparseable payload -> blocking (unchanged fail-closed rule).

DEPENDENCY POINTER: the classifier `_blocking_findings` lives in `mcp-servers/loop-gov-mcp.py` and is
exercised here through the module's own exported function; this file is test-side proof of the
boundary, not a copy of the rule. The store, git and network are not needed.
"""
import importlib.util
import json
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_sibling_class", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

REVIEWED = "app/services/x.rb"
SIBLING = "spec/services/x_spec.rb"


def _finding(**kw):
    base = {
        "finding_id": "F-1",
        "severity": "medium",
        "technique": "unverified-claim",
        "target": REVIEWED + ":10",
        "evidence": "quoted line",
        "recommendation": "commit a re-runnable test",
    }
    base.update(kw)
    return base


def _split(finding, **kw):
    return mcp._blocking_findings(json.dumps([finding]), **kw)


# ── A. the class this change exists for ──────────────────────────────────────
def test_sibling_target_unverified_claim_does_not_block():
    f = _finding(
        target=SIBLING + ":20",
        recommendation="No change to THIS file is required; the resolution belongs to the sibling's own review.",
    )
    blocking, annotating = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert blocking == [], "a finding aimed at a sibling must not refuse this close"
    assert len(annotating) == 1
    assert annotating[0].get("severity_downgraded"), "the downgrade is recorded, not inferred"


def test_downgrade_is_tagged_with_the_original_severity():
    f = _finding(severity="high", target=SIBLING + ":20")
    _, annotating = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert "high" in annotating[0]["severity_downgraded"]


# ── B. the reviewed path wins ────────────────────────────────────────────────
def test_target_naming_the_reviewed_path_still_blocks():
    f = _finding(target=REVIEWED + ":10")
    blocking, _ = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert len(blocking) == 1


def test_target_naming_both_reviewed_and_sibling_still_blocks():
    f = _finding(target=REVIEWED + ":10 (see " + SIBLING + ":20)")
    blocking, _ = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert len(blocking) == 1, "a target that names the judged file must never be downgraded"


# ── C. only the one technique is in scope ────────────────────────────────────
def test_other_techniques_are_never_downgraded():
    for tech in ("fabrication", "injection", "swallowed-error", "scope-drift",
                 "evaluation-awareness", "misattribution"):
        f = _finding(technique=tech, target=SIBLING + ":20")
        blocking, _ = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
        assert len(blocking) == 1, f"{tech} must keep its severity"


def test_critical_severity_sibling_claim_still_downgrades():
    # The class is defined by technique + target, not by severity; a critical-labelled sibling claim
    # is still a window complaint. Recorded explicitly so the boundary is not left to inference.
    f = _finding(severity="critical", target=SIBLING + ":20")
    blocking, annotating = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert blocking == [] and len(annotating) == 1


# ── D/E/F. what must keep blocking ───────────────────────────────────────────
def test_prose_target_still_blocks():
    f = _finding(target="Worker's note: hedging about cutover conditions")
    blocking, _ = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert len(blocking) == 1, "a target naming no path is not a sibling claim"


def test_absent_sibling_context_still_blocks():
    f = _finding(target=SIBLING + ":20")
    blocking, _ = _split(f)
    assert len(blocking) == 1, "no sibling list means no downgrade — fail closed"


def test_empty_sibling_set_still_blocks():
    f = _finding(target=SIBLING + ":20")
    blocking, _ = _split(f, siblings=set(), reviewed_path=REVIEWED)
    assert len(blocking) == 1


def test_unparseable_payload_still_blocks():
    blocking, annotating = mcp._blocking_findings("{not json", siblings={SIBLING}, reviewed_path=REVIEWED)
    assert len(blocking) == 1 and annotating == []


def test_missing_severity_still_blocks():
    f = _finding(target=SIBLING + ":20")
    del f["severity"]
    blocking, _ = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
    assert len(blocking) == 1


def test_info_and_low_stay_annotating():
    for sev in ("info", "low"):
        f = _finding(severity=sev, target=REVIEWED + ":10")
        blocking, annotating = _split(f, siblings={SIBLING}, reviewed_path=REVIEWED)
        assert blocking == [] and len(annotating) == 1


# ── G. the same classifier decides COVERAGE ──────────────────────────────────
# Coverage and the close must ask the same question with the same context: a blob whose only
# findings are aimed at a sibling needs no fix, so it is covered. Left unwired it would read as
# "0 blocking findings" to the close and "carries no review verdict" to the receipt at once.
import sqlite3 as _sqlite3

_DDL = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT, rules_rev TEXT)"""

SHA_REVIEWED, SHA_SIBLING = "sha-reviewed", "sha-sibling"
BLOBS = {REVIEWED: SHA_REVIEWED, SIBLING: SHA_SIBLING}


def _store(findings):
    con = _sqlite3.connect(":memory:")
    con.execute(_DDL)
    con.execute(
        "INSERT INTO blob_reviews (blob_sha, verdict, findings_json, summary, reviewer_id,"
        " reviewer_model, ts, rules_rev) VALUES (?,?,?,?,?,?,?,?)",
        (SHA_REVIEWED, "FINDINGS", json.dumps(findings), "", "r", "m", "2026-01-01", "R"))
    con.commit()
    return con


def test_a_sibling_only_blob_is_covered():
    con = _store([_finding(target=SIBLING + ":20")])
    covered = mcp._blobs_with_covered_verdict(BLOBS, conn=con, rules_rev="R")
    assert SHA_REVIEWED in covered, "a sibling-only finding must not make a blob uncoverable"


def test_a_blob_with_a_finding_on_itself_is_not_covered():
    con = _store([_finding(target=REVIEWED + ":10")])
    covered = mcp._blobs_with_covered_verdict(BLOBS, conn=con, rules_rev="R")
    assert SHA_REVIEWED not in covered


def test_coverage_still_requires_the_current_rules_revision():
    con = _store([_finding(target=SIBLING + ":20")])
    covered = mcp._blobs_with_covered_verdict(BLOBS, conn=con, rules_rev="DIFFERENT")
    assert covered == set(), "an inadmissible verdict covers nothing"
