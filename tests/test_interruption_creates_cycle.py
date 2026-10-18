#!/usr/bin/env python3
"""A sub-task created by request_interruption must have its OWN scorable cycle.

WHY THIS FILE EXISTS (measured deadlock, 2026-10-18, task events #167/#168). An operator priority
change was handled with `request_interruption`, a sanctioned tool. It suspended the parent task
and renamed the lock's task_id to `<parent>_sub1` — and created NO loop_cycles row. The session
then held a LIVE lock that nothing could score, and every exit returned the other exit's
precondition:

  end_change('..._sub1')  -> "Cannot release lock: no governance cycle found for this task.
                              A cycle must be created (via any write tool under this lock)..."
  begin_change(<new>)     -> "A governance session is already active: task_id ..._sub1 ...
                              Call end_change('..._sub1') first, or use force=True to override."

The first instruction was false as shipped: `cycle_query(task_id='..._sub1')` returned `[]` and
the writes made under that lock created no cycle, because cycles come from `begin_change` — which
the second message refuses. The only named exit was `force=True`, which the operator rejects.

WHAT IS PINNED, and why each case is here rather than a source grep:
  * the CREATE path is ONE implementation, shared by begin_change and request_interruption;
  * it writes a PENDING row naming the task and the session it was given, against a redirected store;
  * cycle_num is per TASK (an unrelated task starts at 1) and sequential within a task;
  * an EMPTY session id still writes a scorable row rather than raising;
  * the HANDLER, driven for real, gives the sub-task a cycle and stacks the parent;
  * the HANDLER is FAIL-CLOSED: with the create constructed to fail it REFUSES the interruption
    and leaves the lock naming the PARENT — asserted by driving the handler, not by reading for
    the word "Cannot interrupt";
  * the sandbox never touches the live store (a leaked PENDING cycle is a host-wide doctor
    failure for every agent, not a local inconvenience).

Run: python3 tests/test_interruption_creates_cycle.py

The discrimination re-runs from git history — point it at ANY revision of the server and it must
fail there (the pre-change server has no shared create path and no cycle for a sub-task):

    git show <pre-fix-rev>:mcp-servers/loop-gov-mcp.py > /tmp/loop-gov.pre-fix.py
    SERVER_UNDER_TEST=/tmp/loop-gov.pre-fix.py python3 tests/test_interruption_creates_cycle.py  # rc=1
    python3 tests/test_interruption_creates_cycle.py                                             # rc=0
"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))
LIVE_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
SID = "sess-test"


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_interrupt_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandbox(mod):
    """Point BOTH the store and the lock directory at throwaway paths.

    Both, or neither: a test that redirects the DB but writes its lock into the live state dir
    leaves a real `.governance-*.json` behind, and one that redirects the state dir but inserts
    into the live DB leaves a PENDING cycle the doctor counts as a host failure.
    """
    root = Path(tempfile.mkdtemp(prefix="interrupt-cycle-"))
    mod.LOOP_DB = root / "loop.db"
    # _SCHEMA_DONE is a per-process SET of initialised store paths (not a flag): CLEAR it, or the
    # temp DB is treated as already-initialised and the insert fails on a missing table.
    mod._SCHEMA_DONE.clear()
    mod.GOVERNANCE_STATE_DIR = root / "state"
    mod.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return root


def _rows(mod, task_id):
    conn = sqlite3.connect(str(mod.LOOP_DB))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, task_id, cycle_num, decision, session_id FROM loop_cycles "
            "WHERE task_id=? ORDER BY id", (task_id,))]
    finally:
        conn.close()


def _lock(mod):
    return json.loads((mod.GOVERNANCE_STATE_DIR / f".governance-{SID}.json").read_text())


def _write_parent_lock(mod, task_id="parent-task"):
    """The state a real session is in when the operator interrupts it."""
    (mod.GOVERNANCE_STATE_DIR / f".governance-{SID}.json").write_text(json.dumps({
        "task_id": task_id, "description": "the parent work", "repo_slug": "hermes-cortex",
        "session_id": SID, "status": "executing", "started_at": "2026-10-18T00:00:00Z",
        "heartbeat_at": "2026-10-18T00:00:00Z", "task_stack": [], "acceptance_criteria": [],
        "allowed_scope": [], "plan": [], "ttl_seconds": 3600,
    }))
    return task_id


def test_a_created_cycle_names_its_task_and_is_PENDING():
    """The contract the whole deadlock turned on: after the create call, the task the LOCK names
    has a PENDING cycle to score."""
    mod = _mod()
    _sandbox(mod)
    cid = mod._create_pending_cycle("parent_sub1", SID, "created by the test")
    rows = _rows(mod, "parent_sub1")
    assert len(rows) == 1, rows
    assert rows[0]["decision"] == "PENDING", f"a scorable cycle must start PENDING: {rows[0]}"
    assert rows[0]["session_id"] == SID, rows[0]
    assert rows[0]["id"] == cid, (rows[0], cid)
    print(f"  cycle #{cid} created PENDING for the sub-task id ✓")


def test_cycle_numbers_are_per_task_and_sequential():
    """An auditor reads cycle_num to tell a first attempt from a retry; numbering that leaked
    across tasks would let two unrelated tasks share one sequence."""
    mod = _mod()
    _sandbox(mod)
    a = mod._create_pending_cycle("task-a", SID, "first")
    b = mod._create_pending_cycle("task-a", SID, "second")
    c = mod._create_pending_cycle("task-b", SID, "other task")
    assert [r["cycle_num"] for r in _rows(mod, "task-a")] == [1, 2]
    assert [r["cycle_num"] for r in _rows(mod, "task-b")] == [1], "numbering leaked across tasks"
    assert len({a, b, c}) == 3, (a, b, c)
    print("  per-task sequential numbering (1,2 for a; 1 for b) ✓")


def test_an_empty_session_id_still_writes_a_scorable_row():
    """`state.get("session_id", "")` is empty for locks written by older versions. An empty id must
    still produce a row: refusing to write would recreate the deadlock this file exists for."""
    mod = _mod()
    _sandbox(mod)
    mod._create_pending_cycle("orphan-task", "", "no session recorded")
    rows = _rows(mod, "orphan-task")
    assert len(rows) == 1 and rows[0]["decision"] == "PENDING", rows
    print("  empty session id still yields a PENDING row ✓")


def test_the_handler_gives_the_sub_task_a_cycle_and_stacks_the_parent():
    """The end-to-end case: drive `_request_interruption` itself, not merely a helper it calls."""
    mod = _mod()
    _sandbox(mod)
    parent = _write_parent_lock(mod)
    res = mod._request_interruption({"task_id": parent, "description": "operator priority change",
                                     "reason": "queued work", "session_id": SID})
    text = res.content[0].text
    sub = f"{parent}_sub1"
    assert "Cannot interrupt" not in text, text
    rows = _rows(mod, sub)
    assert rows and rows[0]["decision"] == "PENDING", f"sub-task has no scorable cycle: {rows}"
    lock = _lock(mod)
    assert lock["task_id"] == sub, f"the lock must name the sub-task: {lock['task_id']}"
    assert [s["task_id"] for s in lock["task_stack"]] == [parent], lock["task_stack"]
    assert str(rows[0]["id"]) in text, "the reply must name the cycle the operator has to score"
    print(f"  handler: sub-task cycle #{rows[0]['id']} PENDING, parent stacked ✓")


def test_the_handler_REFUSES_when_the_cycle_cannot_be_created():
    """CONSTRUCTED failure, not a source grep. A refused interruption costs a retry; a lock whose
    task has no scorable cycle costs the session (the measured deadlock). So the lock must still
    name the PARENT after a failed create — a refusal that half-applied is worse than none."""
    mod = _mod()
    _sandbox(mod)
    # Initialise the schema FIRST: the create is about to be replaced with a failure, so nothing
    # else would run _ensure_schema and the "no cycle was written" assertion would fail on a
    # missing TABLE rather than on the refusal it is testing (a probe that fails for the wrong
    # reason is not evidence).
    mod._db().close()
    parent = _write_parent_lock(mod)

    def _boom(*a, **k):
        raise RuntimeError("store unavailable (constructed)")

    original = mod._create_pending_cycle
    mod._create_pending_cycle = _boom
    try:
        res = mod._request_interruption({"task_id": parent, "description": "will not happen",
                                         "session_id": SID})
    finally:
        mod._create_pending_cycle = original
    text = res.content[0].text
    assert "Cannot interrupt" in text, text
    assert "store unavailable" in text, "the refusal must carry the cause: " + text
    lock = _lock(mod)
    assert lock["task_id"] == parent, \
        f"a refused interruption must leave the parent lock intact, found {lock['task_id']}"
    assert lock.get("task_stack") == [], "the parent must not be stacked by a refused interruption"
    assert _rows(mod, f"{parent}_sub1") == [], "no cycle may exist for a refused interruption"
    print("  refused interruption leaves the parent lock and stack untouched ✓")


def test_the_create_happens_BEFORE_the_lock_names_the_sub_task():
    """Ordering is the fix, not just the call: creating the cycle after the rewrite leaves the
    deadlocked state behind whenever the write fails."""
    handler = SERVER.read_text().split("def _request_interruption(args: dict)", 1)[1]
    handler = handler.split("\ndef ", 1)[0]
    assert "_create_pending_cycle(" in handler, "the handler must create the sub-task's cycle"
    assert handler.index("_create_pending_cycle(") < handler.index("_write_lock_and_log("), \
        "the cycle must be created BEFORE the lock names the sub-task"
    print("  cycle created before the lock ✓")


def test_begin_change_uses_the_SAME_implementation():
    """Two copies is how the two paths drifted in the first place: the create was inlined in
    begin_change and simply absent from request_interruption."""
    src = SERVER.read_text()
    assert "def _create_pending_cycle(" in src, "the shared create path is missing"
    begin = src.split("def _begin_change(args: dict)", 1)[1].split("\ndef ", 1)[0]
    assert "_create_pending_cycle(" in begin, "begin_change must use the shared create path"
    assert "INSERT INTO loop_cycles" not in begin, \
        "begin_change must not keep its own INSERT — a second copy is how the paths drift"
    print("  one create path, shared by both entry points ✓")


def test_the_sandbox_never_touches_the_live_store():
    """A regression test must exercise the DETECTOR, not live ambient state — and a leaked PENDING
    cycle is a host-wide doctor failure, not a local inconvenience."""
    mod = _mod()
    _sandbox(mod)
    assert Path(mod.LOOP_DB) != LIVE_DB, "the test must not point at the live store"
    before = LIVE_DB.stat().st_mtime if LIVE_DB.exists() else None
    mod._create_pending_cycle("sandboxed-task", SID, "must not reach the live DB")
    after = LIVE_DB.stat().st_mtime if LIVE_DB.exists() else None
    assert before == after, "the live store was written by a sandboxed test"
    print("  live store untouched (mtime unchanged) ✓")


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
