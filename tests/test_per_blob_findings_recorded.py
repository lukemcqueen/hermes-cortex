#!/usr/bin/env python3
"""One decision must be ONE record: a per-blob FINDINGS verdict has a cycle row too.

WHY THIS FILE EXISTS. Blob verdicts live in `blob_reviews`, keyed by blob sha. `rereview_change`
— the DOCUMENTED exit from a FINDINGS verdict — reads `adversarial_reviews`, keyed by cycle_id.
A close refused on a per-blob pass wrote only the blob rows, so the two stores disagreed about
whether the decision existed at all. Measured on cycle 13253: refused three times on per-blob
findings, and `rereview_change` answered "Cycle #13253 has no recorded review — nothing to
re-review". The exit was unreachable exactly when the findings came from a per-blob pass, which is
now MOST closes. The same defect made the judge invisible: the per-blob writer passed no model, so
all 144 rows read back with an empty `reviewer_model` and nothing in the record said which model
produced a verdict.

WHAT IS PINNED
  * `_record_review` with `replace=True` leaves exactly ONE verdict per cycle (a re-judge must not
    inflate history, and must not silently become a SECOND row the reader has to choose between);
  * the row it writes NAMES the model, so "which judge decided this" is answerable at cycle level;
  * the per-blob blocking branch records that row before it refuses (wiring — asserted on the
    source, because the alternative is standing up a repo and a push range to drive one branch);
  * `rereview_change` can FIND the cycle afterwards — the consumer end, which is what was broken.

Run: python3 tests/test_per_blob_findings_recorded.py
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))
LIVE_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_records_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandbox(mod):
    root = Path(tempfile.mkdtemp(prefix="per-blob-record-")) / "loop.db"
    mod.LOOP_DB = root
    mod._SCHEMA_DONE.clear()
    mod._db().close()
    return root


def _rows(mod, cycle_id):
    conn = sqlite3.connect(str(mod.LOOP_DB))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT cycle_id, verdict, reviewer_model, findings_json FROM adversarial_reviews "
            "WHERE cycle_id=?", (cycle_id,))]
    finally:
        conn.close()


def test_one_verdict_per_cycle_even_when_replaced():
    """A re-judge replaces; it does not append. Two rows for one cycle would make 'the verdict'
    ambiguous to every reader, including the push gate."""
    mod = _mod()
    _sandbox(mod)
    mod._record_review(4242, "per-blob", "deepseek/deepseek-v4-pro", "FINDINGS",
                       '[{"finding_id": "F-1", "severity": "high"}]', "first pass")
    mod._record_review(4242, "per-blob", "deepseek/deepseek-v4-pro", "CLEAN", "[]",
                       "second pass", replace=True)
    rows = _rows(mod, 4242)
    assert len(rows) == 1, f"exactly one verdict per cycle, got {len(rows)}: {rows}"
    assert rows[0]["verdict"] == "CLEAN", rows[0]
    print("  re-judge replaces: still exactly one row ✓")


def test_the_cycle_row_names_the_model_that_decided():
    """The judge must be readable at cycle level too, not only per blob — otherwise a worker
    contesting a verdict cannot say which model produced it."""
    mod = _mod()
    _sandbox(mod)
    mod._record_review(4243, "per-blob", "deepseek/deepseek-v4-pro", "FINDINGS",
                       '[{"finding_id": "F-1", "severity": "high"}]', "per-blob pass", replace=True)
    rows = _rows(mod, 4243)
    assert rows and rows[0]["reviewer_model"] == "deepseek/deepseek-v4-pro", rows
    print("  the cycle verdict names its judge ✓")


def test_rereview_change_can_FIND_the_cycle():
    """The consumer end — the thing that was actually broken. A recorded per-blob verdict must be
    findable by the tool whose job is to re-judge it."""
    mod = _mod()
    _sandbox(mod)
    mod._record_review(4244, "per-blob", "deepseek/deepseek-v4-pro", "FINDINGS",
                       '[{"finding_id": "F-1", "severity": "high"}]', "per-blob pass", replace=True)
    res = mod._rereview_change({"cycle_id": 4244, "task_id": "t", "note": "fixed: see the commit"})
    text = res.content[0].text if hasattr(res, "content") else str(res)
    assert "no recorded review" not in text.lower(), \
        f"rereview_change must find a recorded per-blob verdict: {text[:300]}"
    print("  rereview_change finds the recorded cycle verdict ✓")


def test_the_per_blob_refusal_RECORDS_the_cycle_verdict():
    """Wiring, asserted on the source: the recording has to happen BEFORE the refusal, or a close
    refused this way leaves the two stores disagreeing again."""
    src = SERVER.read_text()
    guard = src.split("if pb.get(\"blocking\"):", 1)
    assert len(guard) == 2, "the per-blob blocking branch is gone — re-anchor this test"
    branch = guard[1].split("return CallToolResult", 1)[0]
    assert "_record_review(" in branch, \
        "the per-blob blocking branch must record a CYCLE-level verdict, or rereview_change " \
        "cannot reach a close refused on per-blob findings"
    assert branch.index("_record_review(") < branch.index("_mark_close_refused("), \
        "record the verdict before marking the lock, so a crash cannot leave one without the other"
    print("  per-blob refusal records the cycle verdict before refusing ✓")


def test_the_live_store_is_untouched():
    mod = _mod()
    _sandbox(mod)
    assert Path(mod.LOOP_DB) != LIVE_DB
    before = LIVE_DB.stat().st_mtime if LIVE_DB.exists() else None
    mod._record_review(9, "per-blob", "m", "CLEAN", "[]", "sandboxed", replace=True)
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
    failed = []
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
