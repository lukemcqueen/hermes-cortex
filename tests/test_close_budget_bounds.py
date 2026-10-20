#!/usr/bin/env python3
"""ONE close, ONE client window — a close must always RETURN a verdict.

Measured 2026-10-18: six ``end_change`` calls each hit the Hermes MCP client ceiling
(300 s) with no verdict at all — not CLEAN, not FINDINGS, not an error the caller could
read (cycles 12777, 12779, 12782, 12792, 12795, 12797; the last three were
documentation-only commits). The cause is arithmetic: a close spent a whole-range
review budget AND THEN a per-blob pass with a budget of its own, and the two together
can exceed the window, so the caller gives up while the server is still working.

The fix is a design bound, not a timeout tweak: the module's own measurement says a
blob call runs 180-220 s (comment at ``BLOB_REVIEW_BUDGET_S``), so within a ~240 s
window **exactly one blob call fits**. A close therefore spends its window on ONE
thing — one blob when unreviewed push-range blobs exist, otherwise the range call —
reports what it did not reach, and the next close continues from the blob-verdict
cache. Every close returns; the work is paid in bounded instalments.

Asserted here, both directions:
  A. the budgets nest under the client window, including their SUM, and the per-window
     blob cap follows from the measured call duration;
  B. the per-blob pass honours the budget it is handed and ACCOUNTS for every blob
     (judged + reported-remaining), so a receipt can name what is uncovered;
  C. the ordinary case is not slowed down: a pass with room finishes every blob.

The store is injected as a collaborator (the store is not what this file judges), so
the test needs no git, no network, no live database, and never calls a governance writer.
"""
import importlib.util
import inspect
import logging as _logging
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_budget", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# Tests must NOT write into the PRODUCTION governance log (the gate's logger appends to
# the live audit trail) — same suppression as test_review_attribution.py.
_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)
_gate_log.handlers.clear()
_gate_log.propagate = False

CLIENT_WINDOW_S = 300  # hermes-agent tools/mcp_tool_common.py _DEFAULT_TOOL_TIMEOUT
MEASURED_BLOB_CALL_S = 200.0  # module's own measurement: blob calls run 180-220 s
_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def test_budgets_nest_under_the_client_window() -> None:
    print("A. the budgets nest under the client window")
    total = getattr(mcp, "CLOSE_TOTAL_BUDGET_S", None)
    _check("a single constant states the close's total budget", total is not None,
           "mcp.CLOSE_TOTAL_BUDGET_S is missing — the sum is unbounded")
    if total is None:
        return
    _check("total < client window", total < CLIENT_WINDOW_S, f"{total} >= {CLIENT_WINDOW_S}")
    _check("per-blob budget <= total", mcp.BLOB_REVIEW_BUDGET_S <= total,
           f"{mcp.BLOB_REVIEW_BUDGET_S} > {total}")
    _check("the two passes' MAXIMA together exceed one window (which is WHY the split rule exists)",
           mcp.REVIEWER_TIMEOUT_CEILING + mcp.BLOB_REVIEW_BUDGET_S >= CLIENT_WINDOW_S,
           "if their sum fit inside one window the split rule would be unnecessary — re-derive "
           "the design. `>=` is correct here and not a typo: at EQUALITY the first pass can still "
           "consume the whole remainder of the window, so the two still cannot BOTH run to "
           "maximum. This check asserts non-fit, not nesting.")
    cap = getattr(mcp, "CLOSE_BLOBS_PER_WINDOW", None)
    _check("a per-window blob cap is stated", cap is not None, "CLOSE_BLOBS_PER_WINDOW missing")
    if cap is not None:
        _check("the cap follows from the measured call duration (one 200 s call fits 240 s)",
               cap * MEASURED_BLOB_CALL_S <= total < (cap + 1) * MEASURED_BLOB_CALL_S,
               f"cap={cap} total={total}: {cap * MEASURED_BLOB_CALL_S} <= {total} < "
               f"{(cap + 1) * MEASURED_BLOB_CALL_S}")


def test_budget_left_helper() -> None:
    print("B. the remaining-budget helper is arithmetic, never negative")
    left = getattr(mcp, "_close_budget_left", None)
    _check("helper exists", left is not None, "mcp._close_budget_left missing")
    if left is None:
        return
    fresh = left(time.monotonic(), total=240.0)
    _check("a fresh close has ~the whole budget", 235.0 < fresh <= 240.0, f"{fresh}")
    spent = left(time.monotonic() - 10.0, total=240.0)
    _check("ten seconds spent leaves ~230", 225.0 < spent < 235.0, f"{spent}")
    _check("an overrun is 0, never negative", left(time.monotonic() - 10000.0, total=240.0) == 0.0)


def test_per_blob_pass_accounts_for_every_blob() -> None:
    print("C. the per-blob pass stops at its budget and accounts for every blob")
    material_for = lambda sha, path: f"material for {path}"  # noqa: E731
    mcp._blobs_with_clean_verdict = lambda blobs, conn=None, **kw: set()
    mcp._record_blob_review = lambda sha, *a, **k: None

    def _ok(sha, path, material):
        return '{"verdict": "CLEAN", "findings": []}'

    blobs = {f"f{i}.txt": f"sha{i}" for i in range(4)}
    got = mcp._review_uncovered_blobs(blobs, reviewer=_ok, material_for=material_for,
                                      cap=99, budget_s=30.0, conn=None)
    _check("with room, every blob is judged", len(got["verdicts"]) == len(blobs),
           f"{len(got['verdicts'])}/{len(blobs)}")
    _check("nothing left over", got["remaining"] == [], str(got["remaining"]))

    def _slow(sha, path, material):
        time.sleep(0.05)
        return '{"verdict": "CLEAN", "findings": []}'

    blobs2 = {f"g{i}.txt": f"s{i}" for i in range(6)}
    started = time.monotonic()
    got2 = mcp._review_uncovered_blobs(blobs2, reviewer=_slow, material_for=material_for,
                                       cap=99, budget_s=0.12, conn=None)
    elapsed = time.monotonic() - started
    _check("a bounded pass returns early", elapsed < 1.0, f"elapsed={elapsed:.2f}s")
    _check("unreached blobs are REPORTED", len(got2["remaining"]) > 0, "nothing reported")
    _check("judged + remaining accounts for every blob",
           len(got2["verdicts"]) + len(got2["remaining"]) == len(blobs2),
           f"{len(got2['verdicts'])}+{len(got2['remaining'])} != {len(blobs2)}")


def test_close_hands_its_remaining_window_to_the_blob_pass() -> None:
    """The close's clock must REACH the blob pass — the wiring, not just the constants.

    The reviewer of cycle 12800 filed a HIGH against the first version of this change for
    exactly this: the constants and the helper existed but nothing on the close path used
    them, so the claimed hand-off of remaining time was not implemented. This drives
    _complete_push_range_blobs with injected collaborators and asserts the two directions:
    a close passes its cap + remaining budget through, and a sweep/CLI caller (no knobs)
    leaves the module defaults untouched.

    SCOPE (reviewer findings ADV-12913-2 and ADV-13059-2): this proves FORWARDING of the values
    the close supplies. The REAL close's own clock read is asserted separately, on its source, by
    test_real_close_reads_its_own_clock_before_handing_the_remainder — which checks that
    _end_change captures a monotonic clock and that the capture PRECEDES the hand-off, since a
    remainder measured from a clock started after the review work would be a larger budget, i.e.
    the original bug. Driving _end_change itself is not attempted here: it needs a live lock and
    a store, and a test that faked both would prove only the fakes.
    """
    print("D. the close hands its remaining window to the blob pass")
    seen: list = []

    mcp._lock_repo = lambda lock: Path("/tmp/repo")            # no git needed
    mcp._range_touches_always_review = lambda repo: True       # do not take the early exit
    mcp._review_template_text = lambda repo: mcp.REVIEW_MARKER + "\n"
    mcp._git_capture = lambda *a, **k: ""
    mcp._agent_author = lambda repo: "the-agent"
    mcp._call_reviewer = lambda *a, **k: "{}"

    def _fake_complete_blob_reviews(repo, template, ctx, run_reviewer, **kw):
        seen.append(kw)
        return {"verdicts": {}, "remaining": [], "calls": 0, "blocking": []}

    _real_complete_blob_reviews = mcp._complete_blob_reviews   # section E needs the REAL one
    mcp._complete_blob_reviews = _fake_complete_blob_reviews

    lock = {"session_id": "test-session", "task_id": "t", "description": "d"}
    mcp._complete_push_range_blobs(lock, {"id": 1}, require_full=True, cap=1, budget_s=123.5)
    _check("the close's cap reaches the pass", bool(seen) and seen[-1].get("cap") == 1, str(seen[-1:]))
    _check("the close's REMAINING budget reaches the pass",
           bool(seen) and seen[-1].get("budget_s") == 123.5, str(seen[-1:]))
    mcp._complete_push_range_blobs(lock, {"id": 1}, require_full=True)
    _check("a caller with no knobs forwards NOTHING (defaults preserved)",
           bool(seen) and "cap" not in seen[-1] and "budget_s" not in seen[-1], str(seen[-1:]))
    # Leave the module as we found it: section E drives the REAL wrapper, and an unrestored
    # fake made E fail against its own double (caught by running the file, 2026-10-18).
    mcp._complete_blob_reviews = _real_complete_blob_reviews


def test_real_wrapper_enforces_the_cap() -> None:
    """The REAL _complete_blob_reviews must ENFORCE cap/budget, not merely accept them.

    Reviewer finding ADV-12913-4: the wiring test below replaces _complete_blob_reviews
    with a fake, so nothing showed the real function accepting and enforcing the knobs.
    This drives the REAL wrapper with git stubbed out and two blobs pending: cap=1 judges
    exactly one and reports the other remaining; cap=2 judges both.
    """
    print("E. the real wrapper enforces the cap it is handed")
    mcp._blobs_with_clean_verdict = lambda blobs, conn=None, **kw: set()
    mcp._record_blob_review = lambda sha, *a, **k: None
    mcp._push_base = lambda repo: "base-sha"
    mcp._push_range_blobs = lambda repo: {"a.txt": "sha-a", "b.txt": "sha-b"}
    mcp._blob_material = lambda repo, base, path, ctx: f"material {path}"

    def _ok(prompt):
        return '{"verdict": "CLEAN", "findings": []}'

    got1 = mcp._complete_blob_reviews(Path("/tmp/repo"), "T\n", {}, _ok, cap=1, budget_s=60.0)
    _check("cap=1 judges exactly one blob", len(got1["verdicts"]) == 1, str(got1["verdicts"]))
    _check("cap=1 reports the other as remaining", len(got1["remaining"]) == 1, str(got1["remaining"]))
    got2 = mcp._complete_blob_reviews(Path("/tmp/repo"), "T\n", {}, _ok, cap=2, budget_s=60.0)
    _check("cap=2 judges both blobs", len(got2["verdicts"]) == 2, str(got2["verdicts"]))


def test_real_close_reads_its_own_clock_before_handing_the_remainder() -> None:
    """The REAL close wires the clock, and in the right ORDER — asserted on its shipped source.

    The forwarding test above proves _complete_push_range_blobs passes through what it is given;
    it cannot prove the close measures its remainder, because driving _end_change needs a live
    lock and a store. This closes that gap honestly rather than by pretending: it reads the
    shipped function and asserts the capture EXISTS and PRECEDES the hand-off. Order is the whole
    point — a remainder computed from a clock started AFTER the review work is a larger budget,
    which is the original defect.
    """
    print("F. the real close reads its own clock, before it hands over the remainder")
    src = inspect.getsource(mcp._end_change)
    capture = "close_started = time.monotonic()"
    handoff = "budget_s=_close_budget_left(close_started)"
    _check("the close captures a monotonic clock", capture in src,
           f"{capture!r} is absent from _end_change — the remainder would be a full window")
    _check("the close hands that remainder to the completion call", handoff in src,
           f"{handoff!r} is absent from _end_change — the clock never reaches the blob pass")
    if capture in src and handoff in src:
        _check("the capture PRECEDES the hand-off", src.index(capture) < src.index(handoff),
               "the clock is read after the hand-off, so what is passed is not a remainder")


if __name__ == "__main__":
    test_budgets_nest_under_the_client_window()
    test_budget_left_helper()
    test_per_blob_pass_accounts_for_every_blob()
    test_close_hands_its_remaining_window_to_the_blob_pass()
    test_real_wrapper_enforces_the_cap()
    test_real_close_reads_its_own_clock_before_handing_the_remainder()
    if _F:
        print(f"\n❌ {len(_F)} close-budget check(s) failed: {', '.join(_F)}")
        sys.exit(1)
    print("\n✅ close-budget checks passed")
    sys.exit(0)
