#!/usr/bin/env python3
"""A `rereview_change` CLEAN must invalidate the per-blob verdicts for the content it judged.

THE DEFECT THIS PINS. `rereview_change` re-runs the reviewer LIVE over the cycle's range and
replaces the row in `adversarial_reviews`. The per-blob verdicts live in `blob_reviews` — a
different store — and were left untouched. A row that is recorded but not covered therefore keeps
its blob on the skip list and in `remaining`, so the close stayed refused on a verdict the
range-level review had already superseded: two stores describing one range, disagreeing about
whether a problem exists. The module already treats that disagreement as a defect class on the
other store (cycle 13253).

THE DIRECTION IS ONE-WAY, and that is the property worth pinning. Rows are DELETED, so the blobs
they described are re-judged live on the next close. They are never marked covered: a rereview may
cost a review, it can never buy coverage. Deleting the whole cache would authorise (by erasure)
content the re-review never saw, so the scope is exactly the range the re-review judged.

WHAT IS PINNED HERE
  A. `_invalidate_range_blob_verdicts` deletes exactly the NOT-covered rows inside the range it is
     given, leaves covered rows alone, leaves out-of-range rows alone, and reports the count;
  B. it fails SAFE: an unresolvable range clears nothing and reports 0;
  C. the cleared blob is ELIGIBLE (re-judged) on the next pass and is NOT covered by the deletion;
  D. `_rereview_change` actually CALLS it after a CLEAN re-review and reports the count in its
     reply — driven end to end with the gate and the lock injected.

Every store here is a throwaway file; the live governance DB is never opened for writing.

Run: python3 tests/test_rereview_clears_stale_blob_verdicts.py
"""
import importlib.util
import logging as _logging
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

REV = "rev-CURRENT"
CLEAN_SHA = "1" * 40        # covered: must SURVIVE
STALE_SHA = "2" * 40        # recorded, not covered: must be CLEARED
OUTSIDE_SHA = "3" * 40      # not in the range: must SURVIVE
RANGE = {"a.rs": CLEAN_SHA, "b.rs": STALE_SHA}


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_rereview_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LOOP_DB = Path(tempfile.mkdtemp(prefix="rereview-")) / "loop.db"
    mod._SCHEMA_DONE.clear()
    return mod


def _seed(mod):
    mod._record_blob_review(CLEAN_SHA, "CLEAN", "[]", "clean", reviewer_id="t", model="t",
                            rules_rev=REV)
    mod._record_blob_review(STALE_SHA, "FINDINGS",
                            '[{"finding_id": "F1", "severity": "high", "technique": "x",'
                            ' "target": "t", "evidence": "e", "recommendation": "r"}]',
                            "blocking", reviewer_id="t", model="t", rules_rev=REV)
    mod._record_blob_review(OUTSIDE_SHA, "FINDINGS",
                            '[{"finding_id": "F2", "severity": "high", "technique": "x",'
                            ' "target": "t", "evidence": "e", "recommendation": "r"}]',
                            "blocking, outside the range", reviewer_id="t", model="t",
                            rules_rev=REV)
    return mod._db()


def _inv(mod):
    """The invalidator, or a NAMED failure — never an AttributeError.

    The pre-fix revision has no such symbol, so a bare attribute access makes this file CRASH
    there instead of reporting what is wrong; a crash is a weaker artifact than a named
    assertion (it also cannot say whether the test reached its subject).
    """
    fn = getattr(mod, "_invalidate_range_blob_verdicts", None)
    assert fn is not None, (
        "_invalidate_range_blob_verdicts is missing — the rereview path has no way to clear a "
        "stale per-blob verdict")
    return fn


def _rows(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT blob_sha, verdict FROM blob_reviews")}


def test_00_preconditions():
    mod = _mod()
    assert hasattr(mod, "_invalidate_range_blob_verdicts"), (
        "_invalidate_range_blob_verdicts is missing — the rereview path has no way to clear a "
        "stale per-blob verdict")
    assert hasattr(mod, "_review_window_base"), (
        "_review_window_base is missing — the rereview path and the review gate would then resolve "
        "the judged range from TWO implementations")


def test_clears_only_uncovered_rows_inside_the_range():
    """A. Scope: exactly the stale row, nothing else."""
    mod = _mod()
    conn = _seed(mod)
    mod._range_blobs = lambda repo, base, head: dict(RANGE)

    cleared = _inv(mod)(Path("/tmp/repo"), "base-sha", rules_rev=REV)
    left = _rows(conn)

    assert cleared == 1, f"expected exactly one stale row cleared, got {cleared}"
    assert STALE_SHA not in left, f"the not-covered row inside the range must be deleted: {left}"
    assert CLEAN_SHA in left, (
        "a COVERED verdict is evidence about this content and must survive — deleting it would "
        f"spend a review for nothing: {left}")
    assert OUTSIDE_SHA in left, (
        f"a row outside the re-reviewed range was never judged by this rereview: {left}")


def test_an_unresolvable_range_clears_nothing():
    """B. Fail safe: no range, no deletion."""
    mod = _mod()
    conn = _seed(mod)
    mod._range_blobs = lambda repo, base, head: None

    cleared = _inv(mod)(Path("/tmp/repo"), "base-sha", rules_rev=REV)
    assert cleared == 0, f"an unresolvable range must clear nothing, got {cleared}"
    assert STALE_SHA in _rows(conn), "nothing may be deleted when the range cannot be resolved"


def test_the_cleared_blob_is_re_judged_not_covered():
    """C. Deletion buys a REVIEW, never coverage."""
    mod = _mod()
    conn = _seed(mod)
    mod._range_blobs = lambda repo, base, head: dict(RANGE)
    _inv(mod)(Path("/tmp/repo"), "base-sha", rules_rev=REV)

    assert STALE_SHA not in mod._blobs_with_covered_verdict(RANGE, conn=conn, rules_rev=REV), (
        "deleting a row must NOT make the blob covered — that would be a rereview granting "
        "coverage for content nobody read")

    seen = []

    def _reviewer(sha, path, material):
        seen.append(sha)
        return '{"verdict": "CLEAN", "findings": []}'

    mod._review_uncovered_blobs(
        RANGE, reviewer=_reviewer, material_for=lambda sha, path: f"material {path}",
        cap=4, budget_s=240.0, conn=conn, rules_rev=REV)

    assert STALE_SHA in seen, (
        f"the cleared blob must be handed to the reviewer again (it is eligible now): {seen}")
    assert CLEAN_SHA not in seen, (
        f"the still-covered blob must not be re-bought: {seen}")


def test_rereview_calls_the_invalidator_and_reports_the_count():
    """D. Wiring: a CLEAN re-review clears the stale verdicts and says so."""
    mod = _mod()
    conn = _seed(mod)
    conn.close()

    calls = []
    mod._verify_lock_for_task = lambda task_id, args: (
        {"session_id": "s", "task_id": task_id, "repo_path": "/tmp/repo"}, None)
    mod._adversarial_review_gate = lambda lock, cycle, force=False, **kw: None    # CLEAN
    mod._lock_repo = lambda lock: Path("/tmp/repo")
    mod._review_template_text = lambda repo: mod.REVIEW_MARKER + "\n"
    mod._rules_rev = lambda text: REV      # the fixture's rows are stamped with THIS revision
    mod._review_window_base = lambda repo, lock: "base-sha"

    real = _inv(mod)

    def _spy(repo, base, *, rules_rev=""):
        got = real(repo, base, rules_rev=rules_rev)
        calls.append({"repo": repo, "base": base, "rules_rev": rules_rev, "cleared": got})
        return got

    mod._invalidate_range_blob_verdicts = _spy
    mod._range_blobs = lambda repo, base, head: dict(RANGE)

    # The cycle row and its FINDINGS review are what rereview reads before re-judging. The columns
    # are NOT NULL in the real schema, so the row is built from the module's own CREATE TABLE rather
    # than a guess (a fixture that omits one fails on the constraint, not on the behaviour).
    db = mod._db()
    db.execute("INSERT OR REPLACE INTO loop_cycles"
               " (id, timestamp, task_id, cycle_num, completeness, quality, progress, composite,"
               "  decision, outcome_note)"
               " VALUES (?,?,?,?,?,?,?,?,?,?)",
               (4242, "2026-01-01", "t", 1, 8.0, 8.0, 8.0, 8.0, "LOOP",
                "an older note about the change"))
    db.commit()
    db.close()
    # Seed the FINDINGS verdict with the module's OWN writer (it creates the table exactly as the
    # reviewer script does) rather than hand-rolling DDL a fixture can get wrong.
    mod._record_review(4242, "t/judge", "t/judge", "FINDINGS",
                       '[{"finding_id": "F0", "severity": "high"}]', "older findings")

    res = mod._rereview_change({"task_id": "t", "note": "NEW note: the finding was fixed; "
                                                       "see the committed test output"})
    text = "\n".join(c.text for c in res.content if getattr(c, "text", None))

    assert calls, "rereview_change returned CLEAN without invalidating the per-blob verdicts"
    assert calls[-1]["base"] == "base-sha", (
        f"the invalidation must cover the range the re-review judged: {calls[-1]}")
    assert calls[-1]["cleared"] == 1, f"expected one stale verdict cleared: {calls[-1]}"
    assert "1" in text and "blob" in text.lower(), (
        f"the reply must report how many per-blob verdicts it cleared:\n{text}")

    left = _rows(mod._db())
    assert STALE_SHA not in left, f"the stale verdict must be gone from the store: {left}"


mod_global = _mod()

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
    sys.exit(1 if fails else 0)
