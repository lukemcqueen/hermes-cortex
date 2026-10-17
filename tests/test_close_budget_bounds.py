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
    _check("the two passes cannot both run to their maximum in one window",
           mcp.REVIEWER_TIMEOUT_CEILING + mcp.BLOB_REVIEW_BUDGET_S >= CLIENT_WINDOW_S,
           "if they fit, the split rule is unnecessary — re-derive the design")
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
    mcp._blobs_with_clean_verdict = lambda blobs, conn=None: set()
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


if __name__ == "__main__":
    test_budgets_nest_under_the_client_window()
    test_budget_left_helper()
    test_per_blob_pass_accounts_for_every_blob()
    if _F:
        print(f"\n❌ {len(_F)} close-budget check(s) failed: {', '.join(_F)}")
        sys.exit(1)
    print("\n✅ close-budget checks passed")
    sys.exit(0)
