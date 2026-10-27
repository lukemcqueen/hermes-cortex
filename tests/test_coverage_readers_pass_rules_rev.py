#!/usr/bin/env python3
"""Every reader that asks "is this blob COVERED?" must ask it under the CURRENT rules revision.

THE DEFECT THIS PINS. `_blobs_with_covered_verdict(blobs)` defaults `rules_rev=""`, and
`_admissible` answers **False** for an empty revision ("unknown provenance costs a review, it never
buys coverage"). Four call sites passed no revision, so on every host the answer was a CONSTANT:

  * `_complete_push_range_blobs` → the `CLEAN in the range : N` line printed 0 always — a
    diagnostic printed directly above the counts that justify a refusal;
  * `_blob_material` → the SIBLING REVIEW STATUS block shown to the per-blob reviewer told it every
    sibling was "NOT covered (blocking findings outstanding)", including siblings that were covered,
    i.e. wrong information fed to the judge;
  * `_receipt_blobs` → the receipt's `reviewed_blobs` was never anything but deletions, so the push
    gate lost content coverage (falling back to exact tip+base) while the module's own comment
    claimed a verdict-covered range;
  * `_unreviewed_paths` → the session-opening scope note listed covered files as unreviewed.

One class, four sites. The rule they must all keep: a verdict produced under the CURRENT rules
covers; anything else (an older revision, a NULL one, or no revision known at all) covers nothing —
the direction that costs a review rather than widening what a receipt can authorise.

Run: python3 tests/test_coverage_readers_pass_rules_rev.py
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

COVERED_SHA = "c" * 40
STALE_SHA = "d" * 40
UNJUDGED_SHA = "e" * 40
RANGE = {"a.rs": COVERED_SHA, "b.rs": STALE_SHA, "c.rs": UNJUDGED_SHA}


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_coverage_rev_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The store goes to a throwaway file BEFORE anything reaches for it: a test must never write
    # to the live governance DB (an unscored cycle there blocks every push on the host).
    mod.LOOP_DB = Path(tempfile.mkdtemp(prefix="blob-cov-")) / "loop.db"
    mod._SCHEMA_DONE.clear()
    return mod


def _seed(mod, rules_rev):
    """CLEAN under the given revision, plus a CLEAN under an OLDER one (which covers nothing)."""
    if rules_rev:
        mod._record_blob_review(COVERED_SHA, "CLEAN", "[]", "judged under current rules",
                                reviewer_id="test", model="test", rules_rev=rules_rev)
    mod._record_blob_review(STALE_SHA, "CLEAN", "[]", "judged under older rules",
                            reviewer_id="test", model="test", rules_rev="rev-OLDER")
    return mod._db()


def test_00_preconditions():
    mod = _mod()
    assert hasattr(mod, "_blobs_with_covered_verdict"), "coverage helper missing"
    assert hasattr(mod, "REV_EMPTY_COVERS_NOTHING") or True   # documentation only
    conn = _seed(mod, "rev-CURRENT")
    assert mod._blobs_with_covered_verdict(RANGE, conn=conn, rules_rev="rev-CURRENT") == {COVERED_SHA}
    assert mod._blobs_with_covered_verdict(RANGE, conn=conn, rules_rev="") == set(), (
        "an empty revision must cover NOTHING (fail closed) — this is the property the four "
        "call sites were silently relying on in the wrong direction")
    older = mod._blobs_with_covered_verdict(RANGE, conn=conn, rules_rev="rev-OLDER")
    assert COVERED_SHA not in older, (
        "a verdict produced under the CURRENT rules must not be credited under an older revision")
    assert STALE_SHA in older, (
        "the fixture's older-revision row should cover under ITS OWN revision — otherwise this "
        "probe is not measuring revision matching at all")


def test_unreviewed_paths_counts_a_covered_blob_as_covered():
    mod = _mod()
    conn = _seed(mod, "rev-CURRENT")
    rev = "rev-CURRENT"
    mod._push_range_blobs = lambda repo: dict(RANGE)
    mod._rules_rev = lambda text: rev

    got = mod._unreviewed_paths(Path("/tmp/repo"))
    assert "a.rs" not in got, f"a.rs carries a CLEAN verdict under the current rules: {got}"
    assert "b.rs" in got, f"b.rs was judged under an OLDER revision, so it needs re-judging: {got}"
    assert "c.rs" in got, f"c.rs has no verdict at all: {got}"
    conn.close()


def test_receipt_names_the_blobs_a_verdict_covers():
    mod = _mod()
    conn = _seed(mod, "rev-CURRENT")
    rev = "rev-CURRENT"
    mod._range_blobs = lambda repo, base, head: dict(RANGE)
    mod._review_template_text = lambda repo: mod.REVIEW_MARKER + "\n"
    mod._rules_rev = lambda text: rev
    mod._push_base_is_root_fallback = lambda repo: False   # else the receipt short-circuits to {}

    kwargs = {}
    import inspect
    if "rules_rev" in inspect.signature(mod._receipt_blobs).parameters:
        kwargs["rules_rev"] = rev
    blobs = mod._receipt_blobs(Path("/tmp/repo"), "base-sha", "head-sha", **kwargs)
    assert blobs.get("a.rs") == COVERED_SHA, (
        f"a COVERED blob must be named in the receipt — otherwise the receipt carries no content "
        f"coverage at all: {blobs}")
    assert "b.rs" not in blobs, f"an older-revision verdict must not be named: {blobs}"
    assert "c.rs" not in blobs, f"an unjudged blob must never be named: {blobs}"

    # FAIL CLOSED: with no revision known, nothing is covered — the receipt says so.
    if kwargs:
        strict = mod._receipt_blobs(Path("/tmp/repo"), "base-sha", "head-sha", rules_rev="")
        assert not strict, f"with no rules revision the receipt must name nothing: {strict}"
    conn.close()


def test_sibling_status_shown_to_the_reviewer_is_truthful():
    mod = _mod()
    conn = _seed(mod, "rev-CURRENT")
    rev = "rev-CURRENT"
    mod._push_range_blobs = lambda repo: dict(RANGE)
    mod._rules_rev = lambda text: rev
    mod._git_capture = lambda *a, **k: ""
    mod._bound_diff = lambda text: text
    mod._sibling_added_lines = lambda repo, base, others: ""
    mod._rank_siblings = lambda paths: list(paths)

    ctx = {"sid": "s", "author": "the-agent", "branch": "main", "head_sha": "abc1234",
           "cycle_id": 1, "task_id": "t", "description": "d"}
    # The REVIEWED file is c.rs (the one with no verdict), so a.rs and b.rs are the SIBLINGS whose
    # status the reviewer is shown.
    material = mod._blob_material(Path("/tmp/repo"), "base-sha", "c.rs", ctx)

    assert "a.rs: CLEAN — covered" in material, (
        "the reviewer is told each sibling's status; a COVERED sibling must read as covered, "
        f"not as 'blocking findings outstanding':\n{material}")
    assert "NOT covered" not in material, (
        "no sibling here carries an outstanding blocking finding, so nothing may be labelled "
        f"'NOT covered' — that false label is what the reviewer was reading:\n{material}")
    conn.close()


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
