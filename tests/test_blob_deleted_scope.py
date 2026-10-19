#!/usr/bin/env python3
"""A path that does not exist at the tip cannot be judged — so it must not be demanded.

Reported by Titus (2026-10-19): a stored range base predating a `generator_v4 -> generator` rename
left 153 absent-at-tip paths in the range; every close reported `reviewed this pass: 0` with the same
paths pending, because a non-clean verdict for a path with no content is never re-sent and can never
be satisfied. A demand that no action can meet is not strictness — it is a deadlock, and the only
exit was an override.

Both halves are asserted here:
  A. such a path is NOT in the demand (nothing to show a reviewer, so nothing to demand);
  B. it IS recorded per path in the receipt as covered-by-deletion — otherwise the push gate, which
     queries the same range including the sentinel, would refuse for ever and the deadlock would
     simply move one step later.

Also asserted (reviewer finding ADV-13384-1): the receipt records EVERY deleted path individually —
one entry must not be able to authorise a different path.
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_blob_deleted", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
_logging.getLogger("loop-governance").setLevel(_logging.CRITICAL + 1)

DELETED = mcp.BLOB_DELETED


def test_split_separates_absent_from_reviewable():
    reviewable, deleted = mcp._split_deleted_blobs({
        "generator/keep.py": "a" * 40,
        "generator_v4/gone.py": DELETED,
        "generator_v4/also_gone.py": DELETED,
    })
    assert list(reviewable) == ["generator/keep.py"]
    assert deleted == ["generator_v4/also_gone.py", "generator_v4/gone.py"]


def test_deleted_path_is_not_demanded_but_is_reported(monkeypatch=None):
    """A: the pass must never ask for a verdict on a path that has no diff."""
    seen = {}

    class _P:
        pass

    saved = (mcp._push_base, mcp._push_range_blobs, mcp._review_uncovered_blobs,
             mcp._peer_session_range_paths)
    mcp._push_base = lambda repo: "base"
    mcp._push_range_blobs = lambda repo: {"a/live.py": "b" * 40, "a/gone.py": DELETED}
    mcp._peer_session_range_paths = lambda repo, base, sid: set()

    def _fake_pass(blobs, **kw):
        seen["blobs"] = dict(blobs)
        return {"verdicts": {}, "remaining": [], "calls": 0, "blocking": []}

    mcp._review_uncovered_blobs = _fake_pass
    try:
        result = mcp._complete_blob_reviews(Path("/tmp"), "TPL", {"sid": "s"}, lambda m: "x")
    finally:
        (mcp._push_base, mcp._push_range_blobs, mcp._review_uncovered_blobs,
         mcp._peer_session_range_paths) = saved

    assert "a/gone.py" not in seen["blobs"], "a path with no diff must not reach the reviewer"
    assert "a/live.py" in seen["blobs"], "a real file is still demanded exactly as before"
    assert result["deleted_paths"] == ["a/gone.py"], "the exclusion must be REPORTED, not silent"


def test_every_deleted_path_is_recorded_separately_in_the_receipt():
    """B (ADV-13384-1): per-path recording — one entry cannot authorise another path."""
    saved = (mcp._push_base_is_root_fallback, mcp._range_blobs, mcp._blobs_with_covered_verdict)
    mcp._push_base_is_root_fallback = lambda repo: False
    mcp._range_blobs = lambda repo, base, head: {
        "generator_v4/one.py": DELETED,
        "generator_v4/two.py": DELETED,
        "generator/live.py": "c" * 40,
    }
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None: set()
    try:
        receipt = mcp._receipt_blobs(Path("/tmp"), "base", "head")
    finally:
        (mcp._push_base_is_root_fallback, mcp._range_blobs, mcp._blobs_with_covered_verdict) = saved

    assert receipt == {"generator_v4/one.py": DELETED, "generator_v4/two.py": DELETED}, receipt
    assert "generator/live.py" not in receipt, "an unjudged real file must NOT be named as covered"


def test_a_deleted_entry_is_not_a_verdict_for_content():
    """The value is the sentinel, never a sha or a verdict — it authorises absence, not content."""
    saved = (mcp._push_base_is_root_fallback, mcp._range_blobs, mcp._blobs_with_covered_verdict)
    mcp._push_base_is_root_fallback = lambda repo: False
    mcp._range_blobs = lambda repo, base, head: {"gone.py": DELETED}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None: set()
    try:
        receipt = mcp._receipt_blobs(Path("/tmp"), "base", "head")
    finally:
        (mcp._push_base_is_root_fallback, mcp._range_blobs, mcp._blobs_with_covered_verdict) = saved
    assert receipt == {"gone.py": DELETED}


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
