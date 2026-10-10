#!/usr/bin/env python3
"""A terminal task transition must RELEASE its session; a missing lock must still fail closed.

    python3 tests/test_terminal_transition_releases_session.py     # exit 0 = pass

Why: cycle 12012's task went 'cancelled' and its session lived on with no way out —
end_change ran the self-adversarial review (which refused on a mis-framed cycle) and
request_interruption refuses from a terminal state — so the lock stranded until its
TTL and the next, correctly-named cycle could not start. Two properties fix that, and
both are asserted here in BOTH directions:

  A. advance to a TERMINAL state (completed/cancelled) releases the lock in the same
     call; a non-terminal transition must NOT release it.
  B. with no lock file, a task whose OWN event log says terminal is "already
     released" (not an error), so the close can still run; a task with no such event
     must still report "No active governance lock." — the tolerance must not become a
     blanket permission to work without a lock.

Hermetic: the lock primitives and the DB are monkeypatched, so the test does not
depend on the live state dir, the live DB, or whichever cycle happens to be open.
"""
import importlib.util
import pathlib
import sys

MCP = pathlib.Path(__file__).resolve().parents[1] / "mcp-servers/loop-gov-mcp.py"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def load():
    spec = importlib.util.spec_from_file_location("loopgov_terminal", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def text_of(result):
    return "\n".join(getattr(c, "text", "") for c in result.content)


def main():
    m = load()
    check("terminal states are declared", sorted(m.TERMINAL_STATES), ["cancelled", "completed"])

    # ---- A. the transition itself releases, and only when terminal -------------
    released = []

    def from_state_for(target):
        """A state the module's OWN machine lets transition to `target`."""
        for src, allowed in m.VALID_TRANSITIONS.items():
            if target in allowed and src not in m.TERMINAL_STATES:
                return src
        return None

    real_verify = m._verify_lock_for_task
    current_src = ["executing"]

    def fake_verify(task_id, args=None):
        return {"task_id": task_id, "status": current_src[0]}, ""

    m._verify_lock_for_task = fake_verify
    m._write_lock_and_log = lambda state, event, detail="", args=None: None
    m._release_lock = lambda args=None: released.append(True)

    for target, want_release in (("cancelled", True), ("completed", True),
                                 ("verifying", False), ("reporting", False)):
        src = from_state_for(target)
        if src is None:
            print(f"SKIP  advance -> {target}: no non-terminal source in the machine")
            continue
        current_src[0] = src
        released.clear()
        out = text_of(m._advance_task_state({"task_id": "t1", "new_state": target}))
        check(f"advance {src} -> {target}: released", bool(released), want_release)
        check(f"advance {src} -> {target}: says so in the reply",
              ("Lock released" in out), want_release)
        check(f"advance {src} -> {target}: still reports the transition",
              f"{src} → {target}" in out, True)

    # A transition that is refused by the state machine must not release anything.
    current_src[0] = "executing"
    released.clear()
    out = text_of(m._advance_task_state({"task_id": "t1", "new_state": "planning"}))
    check("invalid transition releases nothing", bool(released), False)
    check("invalid transition is still reported", "Invalid transition" in out, True)

    # ---- B. no lock file: terminal = already released, anything else = error ---
    # The REAL verifier, restored: section A replaced it with a stub.
    m._verify_lock_for_task = real_verify
    m._read_lock = lambda args=None: None

    m._last_task_state = lambda task_id: "cancelled"
    state, err = m._verify_lock_for_task("t2")
    check("terminal task with no lock: no error", err, "")
    check("terminal task with no lock: flagged as released",
          bool(state and state.get("released_by_terminal_transition")), True)

    m._last_task_state = lambda task_id: "executing"
    state, err = m._verify_lock_for_task("t2")
    check("non-terminal with no lock: still fails closed", err, "No active governance lock.")
    check("non-terminal with no lock: no state returned", state, None)

    m._last_task_state = lambda task_id: ""          # no events at all
    state, err = m._verify_lock_for_task("t2")
    check("no events with no lock: still fails closed", err, "No active governance lock.")

    # A lock that exists but belongs to another task must never be tolerated.
    m._read_lock = lambda args=None: {"task_id": "someone-else", "status": "executing"}
    m._last_task_state = lambda task_id: "cancelled"
    state, err = m._verify_lock_for_task("t2")
    check("another task's lock is still refused",
          err, "Lock belongs to task 'someone-else', not 't2'.")

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS — terminal releases the session, and a missing lock "
          "still fails closed for everything that is not terminal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
