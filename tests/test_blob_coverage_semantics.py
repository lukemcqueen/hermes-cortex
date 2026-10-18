#!/usr/bin/env python3
"""Coverage means JUDGED AND NOTHING OUTSTANDING — and what must stay uncovered still does.

Found by draining the unpushed range (2026-10-18): a blob judged with SIX `info` findings read as
"0 blocking findings" to the close and as "carries no review verdict" to the receipt at the same
time, so it could never be covered and the range could never close. Coverage demanded a bare CLEAN
verdict while the close's own gate refused only on BLOCKING findings — a contradiction, not
strictness, and the reason the drain looked infinite.

The two sets answer different questions and must NOT be merged:
  * BLOCKING — unchanged; a blocking finding still refuses the close.
  * COVERED  — "was this content read, and does anything need fixing?"

Asserted here — A and B are the fix, C to E are the protection that must not move:
  A. a CLEAN verdict is covered;
  B. a FINDINGS verdict whose findings are all below blocking is covered, and is therefore NOT
     re-reviewed and NOT reported as outstanding;
  C. a BLOCKING finding is NOT covered;
  D. an UNJUDGED blob is NOT covered (a receipt may never name a file nobody read);
  E. ambiguity fails CLOSED — a missing row, unparseable findings_json, or a FINDINGS verdict with
     an EMPTY findings list is NOT covered ("silence is never CLEAN").

The store is injected, so this needs no git, no network and no live database.
"""
import importlib.util
import json
import logging as _logging
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_coverage", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

DDL = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT)"""

FINDING = {
    "finding_id": "ADV-1-1", "technique": "unverified-claim", "target": "f:1",
    "evidence": "e", "recommendation": "r",
}


def _store(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(DDL)
    for sha, verdict, findings in rows:
        conn.execute("INSERT OR REPLACE INTO blob_reviews (blob_sha, verdict, findings_json, ts) "
                     "VALUES (?,?,?,?)", (sha, verdict, findings, "2026-10-18T00:00:00Z"))
    conn.commit()
    return conn


def _sha(ch):
    return ch * 40


def test_00_preconditions():
    assert hasattr(mcp, "_blobs_with_covered_verdict"), "the coverage helper is missing"
    assert hasattr(mcp, "_blocking_findings"), "the blocking classifier is missing"
    # The classifier must rate the severities this test relies on the way the test assumes.
    for sev, expect_blocking in (("high", True), ("critical", True), ("info", False), ("low", False)):
        raw = json.dumps([dict(FINDING, severity=sev)])
        blocked = bool(mcp._blocking_findings(raw)[0])
        assert blocked == expect_blocking, (
            f"_blocking_findings rates {sev} as blocking={blocked}, but this test assumes "
            f"{expect_blocking} — the coverage rule's boundary moved")


def test_clean_is_covered():
    blobs = {"a.py": _sha("a")}
    assert mcp._blobs_with_covered_verdict(blobs, conn=_store([(_sha("a"), "CLEAN", "[]")])) \
        == {_sha("a")}


def test_non_blocking_findings_are_covered():
    blobs = {"b.py": _sha("b")}
    conn = _store([(_sha("b"), "FINDINGS", json.dumps([dict(FINDING, severity="info")]))])
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == {_sha("b")}, (
        "a blob judged with only non-blocking findings must be COVERED, or it can never be "
        "covered at all (the close reports 0 blocking findings for it)")


def test_blocking_findings_are_not_covered():
    blobs = {"c.py": _sha("c")}
    conn = _store([(_sha("c"), "FINDINGS", json.dumps([dict(FINDING, severity="high")]))])
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == set(), (
        "a blocking finding must NOT be covered — this is the protection that must not move")


def test_unjudged_is_not_covered():
    blobs = {"d.py": _sha("d")}
    assert mcp._blobs_with_covered_verdict(blobs, conn=_store([])) == set(), (
        "an unjudged blob must never be covered: a receipt may not name a file nobody read")


def test_ambiguity_fails_closed():
    rows = [(_sha("e"), "FINDINGS", ""),                       # no findings recorded
            (_sha("f"), "FINDINGS", "not json"),               # unparseable
            (_sha("g"), "FINDINGS", "[]")]                     # empty list = silence
    blobs = {"e.py": _sha("e"), "f.py": _sha("f"), "g.py": _sha("g")}
    got = mcp._blobs_with_covered_verdict(blobs, conn=_store(rows))
    assert got == set(), f"ambiguity must fail CLOSED (covered nothing), got {got}"


def test_covered_blob_is_not_re_reviewed_and_not_outstanding():
    """The integration benefit: a covered blob costs no call and is not reported as outstanding."""
    seen = []

    def reviewer(sha, path, material):
        seen.append(path)
        return '{"verdict": "CLEAN", "findings": []}'

    blobs = {"a/covered.py": _sha("a"), "z/pending.py": _sha("z")}
    conn = _store([(_sha("a"), "FINDINGS", json.dumps([dict(FINDING, severity="info")]))])
    out = mcp._review_uncovered_blobs(blobs, reviewer=reviewer,
                                      material_for=lambda sha, path: "m",
                                      cap=1, budget_s=240.0, conn=conn)
    assert "a/covered.py" not in seen, f"a covered blob must not be re-reviewed: {seen}"
    assert _sha("a") not in out["remaining"], (
        "a covered blob must not be reported as carrying no verdict: " + str(out["remaining"]))
    assert "z/pending.py" in seen, "the cap must go to the blob that is genuinely outstanding"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'FAILED' if fails else 'OK'} — {fails} failure(s)")
    raise SystemExit(1 if fails else 0)
