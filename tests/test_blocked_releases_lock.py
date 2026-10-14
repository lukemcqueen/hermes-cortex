"""A 'blocked' transition must free the lock, and must not strand a PENDING cycle.

Luke 2026-10-14: a lock whose owner cannot progress should be ended or taken over
rather than left to burn its TTL. 'blocked' remains NON-TERMINAL (the task stays
resumable), but it is a STOPPAGE — holding the mutex then prevents the session from
doing any other governed work while other sessions may also need to close. Same
dead-end class as a lock tagged with a repo the session is not working in.

ORDER IS LOAD-BEARING, and is asserted here: the cycle is closed UNSCORED *before* the
lock is dropped. A released lock beside a still-PENDING cycle is a doctor FAIL (leak)
that blocks the push for EVERY agent on the host — measured 2026-10-14, when exactly
one such row was the sole failure behind a refused push. No review receipt is written
on this path, so a blocked change authorises nothing and cannot be pushed from it.

The closing UPDATE itself lives in ONE shared closer, pinned by
tests/test_release_after_refusal_closes_cycle.py; this file asserts the branch CALLS it,
in the right order, and never carries its own copy.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
CLOSER = "_close_cycle_unscored"
UPDATE_MARKER = "SET decision='MOVE_ON', unscored_reason=?"


def _fn_source(name):
    src = SRC.read_text()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(src, node)
            assert segment, f"could not read the source of {name}"
            return segment
    raise AssertionError(f"{name} not found in {SRC}")


def _blocked_branch():
    body = _fn_source("_advance_task_state")
    assert 'elif new_state == "blocked":' in body, "no blocked branch in _advance_task_state"
    return body.split('elif new_state == "blocked":', 1)[1]


def test_blocked_transition_closes_the_cycle_before_releasing_the_lock():
    branch = _blocked_branch()

    assert f"{CLOSER}(" in branch, "the blocked branch must close its cycle through the closer"
    assert UPDATE_MARKER not in branch, (
        "the blocked branch carries its own copy of the closing UPDATE — it must delegate "
        "to the shared closer so the release paths cannot drift apart again"
    )

    # Says plainly that nothing was reviewed, so no reader mistakes it for a close.
    assert "no receipt" in branch

    # Order: cycle first, lock second.
    assert branch.index(f"{CLOSER}(") < branch.index("_release_lock("), (
        "the cycle must be closed unscored BEFORE the lock is released, or the release "
        "leaves a lockless PENDING cycle that fails the doctor for every agent"
    )


def test_blocked_still_releases_the_lock_when_the_store_step_fails():
    """A broken store must not leave the session stuck — that is the dead-end being fixed.

    The closer reports failure instead of raising, and the branch must not gate the
    release on its result: the release runs unconditionally after the call.
    """
    branch = _blocked_branch()
    assert "if _cycle_closed:" not in branch, (
        "the closer's result must not guard the release — a store failure would then "
        "strand the lock, which is the dead-end this branch removes"
    )
    assert branch.index(f"{CLOSER}(") < branch.index("_release_lock(")


def test_blocked_stays_non_terminal_and_is_a_separate_path():
    body = _fn_source("_advance_task_state")
    assert "if new_state in TERMINAL_STATES:" in body
    assert 'elif new_state == "blocked":' in body, (
        "blocked must be its own branch beside the terminal one, never folded into it"
    )

    src = SRC.read_text()
    terminal_lines = [ln for ln in src.splitlines() if ln.startswith("TERMINAL_STATES")]
    assert terminal_lines, "TERMINAL_STATES definition not found"
    for ln in terminal_lines:
        assert "blocked" not in ln, f"'blocked' must stay non-terminal (resumable): {ln}"
