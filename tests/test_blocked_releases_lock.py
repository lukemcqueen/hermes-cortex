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
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"


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

    # Closed UNSCORED, and only ever a still-PENDING, non-overridden row.
    assert "decision='MOVE_ON'" in branch
    assert "unscored_reason=?" in branch
    assert "decision='PENDING'" in branch
    assert "user_overrode IS NULL" in branch

    # Says plainly that nothing was reviewed, so no reader mistakes it for a close.
    assert "no receipt" in branch

    # Order: cycle first, lock second.
    assert branch.index("decision='MOVE_ON'") < branch.index("_release_lock(args)"), (
        "the cycle must be closed unscored BEFORE the lock is released, or the release "
        "leaves a lockless PENDING cycle that fails the doctor for every agent"
    )


def test_blocked_still_releases_the_lock_when_the_db_step_fails():
    """A broken store must not leave the session stuck — that is the dead-end being fixed."""
    branch = _blocked_branch()
    assert branch.index("could not close PENDING cycle") < branch.index("_release_lock(args)")


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
