#!/usr/bin/env python3
"""A sub-task created by request_interruption must have its OWN scorable cycle.

WHY THIS FILE EXISTS (measured deadlock, 2026-10-18, task events #167/#168). An operator
priority change was handled with `request_interruption`, a sanctioned tool. It suspended the
parent task and renamed the lock's task_id to `<parent>_sub1` — and created NO loop_cycles row.
The session then held a LIVE lock that nothing could score, and every exit returned the other
exit's precondition:

  end_change('..._sub1')  -> "Cannot release lock: no governance cycle found for this task.
                              A cycle must be created (via any write tool under this lock)..."
  begin_change(<new>)     -> "A governance session is already active: task_id ..._sub1 ...
                              Call end_change('..._sub1') first, or use force=True to override."

The first instruction was false as shipped: `cycle_query(task_id='..._sub1')` returned `[]` and
the writes made under that lock created no cycle, because cycles come from `begin_change` — which
the second message refuses. The only named exit was `force=True`, which the operator rejects.

Two properties are pinned here:

  1. The CREATE path is ONE implementation shared by begin_change and request_interruption, and it
     writes a PENDING row for the task id it is given, against whatever store is configured.
  2. The interruption is FAIL-CLOSED: if the sub-task's cycle cannot be created it refuses the
     interruption, because a refused interruption costs a retry while a lock with no scorable
     cycle costs the session.

Run: python3 tests/test_interruption_creates_cycle.py

The discrimination re-runs from git history — point it at ANY revision of the server and it must
fail there (the pre-change server has no shared create path and no cycle for a sub-task):

    git show <pre-fix-rev>:mcp-servers/loop-gov-mcp.py > /tmp/loop-gov.pre-fix.py
    SERVER_UNDER_TEST=/tmp/loop-gov.pre-fix.py python3 tests/test_interruption_creates_cycle.py  # rc=1
    python3 tests/test_interruption_creates_cycle.py                                             # rc=0
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))
_ORIG_DB = None


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_interrupt_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _redirect(mod):
    """Point the server's store at a throwaway DB. Never the live store: a test that writes
    PENDING cycles to it leaves rows the doctor counts as failures for every agent on the host."""
    tmp = Path(tempfile.mkdtemp(prefix="interrupt-cycle-")) / "loop.db"
    mod.LOOP_DB = tmp
    # _SCHEMA_DONE is a per-process SET of initialised store paths (not a flag): CLEAR it, or the
    # temp DB is treated as already-initialised and the insert fails on a missing table.
    mod._SCHEMA_DONE.clear()
    return tmp


def test_a_created_cycle_names_its_task_and_is_PENDING():
    """The contract the whole deadlock turned on: after the create call, the task the LOCK names
    has a PENDING cycle to score."""
    mod = _mod()
    tmp = _redirect(mod)
    try:
        cid = mod._create_pending_cycle("parent_sub1", "sess-test", "created by the test")
        conn = sqlite3.connect(str(tmp))
        try:
            row = conn.execute("SELECT task_id, decision, session_id, outcome_note "
                               "FROM loop_cycles WHERE id=?", (cid,)).fetchone()
        finally:
            conn.close()
        assert row is not None, "no cycle row was written"
        assert row[0] == "parent_sub1", row
        assert row[1] == "PENDING", f"a scorable cycle must start PENDING, got {row[1]!r}"
        assert row[2] == "sess-test", row
        print(f"  cycle #{cid} created PENDING for the sub-task id ✓")
    finally:
        mod.LOOP_DB = _ORIG_DB


def test_two_cycles_for_one_task_number_sequentially():
    """`cycle_num` is what an auditor reads to tell a first attempt from a retry."""
    mod = _mod()
    tmp = _redirect(mod)
    try:
        a = mod._create_pending_cycle("t", "s", "first")
        b = mod._create_pending_cycle("t", "s", "second")
        conn = sqlite3.connect(str(tmp))
        try:
            nums = [r[0] for r in conn.execute(
                "SELECT cycle_num FROM loop_cycles WHERE task_id='t' ORDER BY id")]
        finally:
            conn.close()
        assert nums == [1, 2], f"expected sequential cycle numbers, got {nums}"
        assert a != b, (a, b)
        print(f"  two cycles number sequentially: {nums} ✓")
    finally:
        mod.LOOP_DB = _ORIG_DB


def test_the_interruption_creates_the_cycle_before_it_names_the_lock():
    """Ordering is the fix, not just the call. If the lock is written first, a DB failure leaves
    exactly the deadlocked state; the create must come before _write_lock_and_log, and a failure
    must REFUSE the interruption rather than half-create it."""
    src = SERVER.read_text()
    assert "def _create_pending_cycle(" in src, "the shared create path is missing"
    assert src.count("_create_pending_cycle(") >= 3, \
        "the helper must be DEFINED once and CALLED by both begin_change and request_interruption"
    handler = src.split("def _request_interruption(args: dict)", 1)[1]
    handler = handler.split("\ndef ", 1)[0]
    assert "_create_pending_cycle(" in handler, \
        "request_interruption must create the sub-task's cycle"
    assert handler.index("_create_pending_cycle(") < handler.index("_write_lock_and_log("), \
        "the cycle must be created BEFORE the lock names the sub-task"
    assert "Cannot interrupt" in handler, \
        "a failure to create the cycle must REFUSE the interruption (fail closed)"
    print("  cycle created before the lock; failure refuses the interruption ✓")


def test_begin_change_uses_the_SAME_implementation():
    """Two copies is how the two paths drifted apart in the first place: the create was inlined in
    begin_change and simply absent from request_interruption."""
    src = SERVER.read_text()
    begin = src.split("def _begin_change(args: dict)", 1)[1].split("\ndef ", 1)[0]
    assert "_create_pending_cycle(" in begin, "begin_change must use the shared create path"
    assert "INSERT INTO loop_cycles" not in begin, \
        "begin_change must not keep its own INSERT — a second copy is how the paths drift"
    print("  begin_change and request_interruption share ONE create path ✓")


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
