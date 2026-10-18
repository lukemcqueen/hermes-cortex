#!/usr/bin/env python3
"""One close window must judge a WAVE of blobs, not one — and never credit a blob it could not read.

WHY. A blob reviewer call measures 180-220s and the close's window is 240s, so a SEQUENTIAL pass
judges exactly one blob per round trip: closing a 15-file range (cycle 13287) took 15 end_change
calls, the unreviewed count walking 14 -> 13 -> ... -> 1. The calls are independent I/O waits, so
issuing them CONCURRENTLY bounds elapsed time by the SLOWEST call instead of their sum — which is
what lets N blobs earn verdicts inside the SAME window, without raising it. The operator's recorded
requirement ("reviews should be shorter than 300s — the window is never raised") is untouched.

WHAT IS PINNED
  * a wave of N calls, with elapsed time near ONE call's duration, not N times it;
  * `workers=1` still behaves exactly as before (the property the change had to preserve);
  * the cap still bounds calls per pass, and everything not reached is REPORTED in `remaining`
    rather than dropped, so the close still refuses and the next pass continues;
  * a call that fails NEVER credits its blob (it stays in `failed` AND `remaining`) while its
    siblings are still judged — progress, never stop-on-first;
  * enough consecutive failures still means the reviewer is DOWN and defers the rest by name.

The function's `reviewer` is INJECTED, so this is hermetic: no store, no git, no network. The DB is
redirected to a temp file, and the live store is asserted untouched.

Run: python3 tests/test_blob_review_concurrency.py
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))
LIVE_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
SLEEP = 0.8


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_concurrency_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandbox(mod):
    root = Path(tempfile.mkdtemp(prefix="blob-conc-")) / "loop.db"
    mod.LOOP_DB = root
    mod._SCHEMA_DONE.clear()
    mod._db().close()
    return root


def _blobs(n):
    return {f"f{i}.py": f"sha{i}" for i in range(n)}


def _run(mod, n, workers, cap, responder):
    return mod._review_uncovered_blobs(
        _blobs(n),
        reviewer=lambda sha, path, material: responder(sha, path),
        material_for=lambda sha, path: f"material for {path}",
        cap=cap, budget_s=240.0, workers=workers, reviewer_label="test/judge")


def _clean(sha, path):
    time.sleep(SLEEP)
    return '{"verdict": "CLEAN", "findings": []}'


def test_a_wave_judges_N_blobs_in_about_ONE_sleep():
    """The whole point: elapsed is the slowest call, not their sum."""
    mod = _mod()
    _sandbox(mod)
    started = time.monotonic()
    out = _run(mod, 4, workers=4, cap=4, responder=_clean)
    elapsed = time.monotonic() - started
    assert out["calls"] == 4, f"expected 4 blobs judged, got {out['calls']}: {out}"
    assert not out["remaining"], f"all four should be covered: {out['remaining']}"
    assert all(v == "CLEAN" for v in out["verdicts"].values()), out["verdicts"]
    # Four sequential calls would take >= 3.2s; a wave takes ~0.8s.
    assert elapsed < 4 * SLEEP * 0.6, (
        f"a wave must overlap: {elapsed:.2f}s for 4 x {SLEEP}s sleeps is sequential, not concurrent")
    print(f"  4 blobs judged in {elapsed:.2f}s (one sleep is {SLEEP}s) ✓")


def test_workers_1_reproduces_the_previous_sequential_behaviour():
    """The change must not alter what one-at-a-time does."""
    mod = _mod()
    _sandbox(mod)
    started = time.monotonic()
    out = _run(mod, 3, workers=1, cap=3, responder=_clean)
    elapsed = time.monotonic() - started
    assert out["calls"] == 3, out
    assert not out["remaining"], out["remaining"]
    assert elapsed >= 3 * SLEEP * 0.8, (
        f"workers=1 must still run one at a time: {elapsed:.2f}s for 3 sleeps")
    print(f"  workers=1 stays sequential ({elapsed:.2f}s) ✓")


def test_the_cap_still_bounds_a_pass_and_reports_the_rest():
    """Nothing is dropped: the remainder is REPORTED so the close refuses and the next pass
    continues."""
    mod = _mod()
    _sandbox(mod)
    out = _run(mod, 6, workers=4, cap=2, responder=_clean)
    assert out["calls"] == 2, f"the cap must bound the pass, got {out['calls']}: {out}"
    assert len(out["remaining"]) == 4, f"the other four must be reported: {out['remaining']}"
    print("  cap bounds the pass; the remainder is reported ✓")


def test_a_failed_call_never_credits_its_blob_and_does_not_stop_the_others():
    """A failure is an outage, never a pass — and the old stop-on-first made zero progress."""
    mod = _mod()
    _sandbox(mod)

    def flaky(sha, path):
        time.sleep(SLEEP)
        if path == "f1.py":
            raise RuntimeError("reviewer timed out")
        return '{"verdict": "CLEAN", "findings": []}'

    out = _run(mod, 4, workers=4, cap=4, responder=flaky)
    bad = "sha1"
    assert bad in out["failed"], f"the failure must be named: {out['failed']}"
    assert bad in out["remaining"], "a failed blob is NOT covered"
    assert bad not in out["verdicts"] or out["verdicts"].get(bad) != "CLEAN", \
        "a failure must never be credited as CLEAN"
    assert out["calls"] == 3, f"the three healthy blobs must still be judged: {out['calls']}"
    print("  a failure never credits its blob and never stops its siblings ✓")


def test_consecutive_failures_still_mean_the_reviewer_is_DOWN():
    """The outage signal must survive: everything unreached is deferred by name."""
    mod = _mod()
    _sandbox(mod)
    max_fail = mod.BLOB_REVIEW_MAX_CONSECUTIVE_FAILURES

    def dead(sha, path):
        time.sleep(0.05)
        raise RuntimeError("reviewer unreachable")

    out = _run(mod, max_fail + 3, workers=max_fail + 3, cap=max_fail + 3, responder=dead)
    assert out["calls"] == 0, f"a down reviewer credits nothing: {out['calls']}"
    assert len(out["failed"]) >= max_fail, out["failed"]
    assert len(out["remaining"]) == max_fail + 3, (
        f"every unreached blob is deferred by name: {len(out['remaining'])}")
    assert not out["blocking"], "an outage is not a finding"
    print("  a down reviewer credits nothing and defers everything ✓")


def test_the_live_store_is_untouched():
    mod = _mod()
    _sandbox(mod)
    before = LIVE_DB.stat().st_mtime if LIVE_DB.exists() else None
    _run(mod, 2, workers=2, cap=2, responder=_clean)
    after = LIVE_DB.stat().st_mtime if LIVE_DB.exists() else None
    assert before == after, "a sandboxed test wrote the live store"
    print("  live store untouched ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("server:", SERVER)
    assert SERVER.is_file(), f"missing server: {SERVER}"
    failed, not_run = [], []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
