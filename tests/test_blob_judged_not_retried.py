#!/usr/bin/env python3
"""A blob already JUDGED must not be judged again, or it starves the whole range.

Measured 2026-10-18, drain of a 38-blob push range: the per-blob pass walks blobs in
sorted path order and skips only the ones with a CLEAN verdict, so the FIRST blob whose
verdict is FINDINGS is re-sent to the reviewer on every single close. Verdicts are keyed
by blob CONTENT, so re-reviewing identical bytes cannot produce a different answer — the
call is pure waste, and with a per-close cap of ONE blob it also starves every blob
sorted after it. Observed: two consecutive closes each reported
``reviewed this pass : 1 blob(s)`` / ``still carry no review verdict: 10`` with the SAME
content judged again, while ten blobs sat with no verdict at all.

The fix is a skip, not a pass (no enforcement is weakened):
  * a blob with a RECORDED verdict that is not CLEAN is still REPORTED in ``remaining``,
    so the close still refuses and the receipt still names it uncovered — the operator
    must FIX the file and commit (which is a new blob) rather than close in a loop;
  * it is simply not sent to the reviewer a second time for identical content, so the
    per-close cap is spent on blobs that have never been judged.

Asserted here:
  A. a blob carrying a non-clean verdict is not handed to the reviewer, and is named in
     ``judged`` AND in ``remaining`` (fail-closed both ways);
  B. an unjudged blob IS reviewed in the same pass, i.e. the cap is not spent on the
     already-judged blob;
  C. a CLEAN blob is still skipped as before (no regression to the existing cache path).

The store is injected, so this test needs no git, no network and no live database.
"""
import importlib.util
import logging as _logging
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_judged", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# The gate's logger appends to the live audit trail; a test must not write there.
_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

DDL = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT)"""


def _store(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(DDL)
    for sha, verdict in rows:
        conn.execute("INSERT OR REPLACE INTO blob_reviews (blob_sha, verdict, ts) VALUES (?,?,?)",
                     (sha, verdict, "2026-10-18T00:00:00Z"))
    conn.commit()
    return conn


def _run(blobs, conn):
    seen = []

    def reviewer(sha, path, material):
        seen.append((path, sha))
        return '{"verdict": "CLEAN", "findings": []}'

    out = mcp._review_uncovered_blobs(
        blobs, reviewer=reviewer,
        material_for=lambda sha, path: f"material for {path}",
        cap=1, budget_s=240.0, conn=conn)
    return out, seen


def test_judged_blob_is_not_reviewed_again_and_still_blocks():
    judge_me, already = "b" * 40, "a" * 40
    blobs = {"a/one.txt": already, "z/two.txt": judge_me}
    conn = _store([(already, "FINDINGS")])
    out, seen = _run(blobs, conn)

    assert already not in [s for _, s in seen], (
        "a blob that already carries a verdict must not be re-sent: identical content "
        f"cannot produce a different verdict. reviewer saw {seen}")
    assert already in out["judged"], (
        f"the already-judged blob must be REPORTED so the close can name it: {out}")
    assert already in out["remaining"], (
        "a non-clean verdict is NOT coverage: the blob must still count as uncovered "
        f"so the receipt cannot claim it: {out}")
    assert judge_me in [s for _, s in seen], (
        "the cap must be spent on a blob nobody has judged: " + str(seen))


def test_clean_blob_is_still_skipped():
    clean, unjudged = "c" * 40, "d" * 40
    blobs = {"a/clean.txt": clean, "z/new.txt": unjudged}
    out, seen = _run(blobs, _store([(clean, "CLEAN")]))
    assert clean not in [s for _, s in seen]
    assert out["verdicts"].get(clean) == "CLEAN"
    assert unjudged in [s for _, s in seen]


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
