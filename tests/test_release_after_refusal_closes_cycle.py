"""A release-first refusal must not strand the PENDING cycle it walked away from.

Measured 2026-10-14 (this falsified a claim in a review brief): ``_release_after_refusal``
freed the lock on a FINDINGS refusal but never touched the ``loop_cycles`` row, so the
cycle stayed PENDING with NO live lock — a doctor FAIL (leak) that blocks the push for
EVERY agent on the host. It is the same leak the metadata-refusal fix closed one branch
over (cycle 12538, one such row, was the sole failure behind a refused push).

Pinned here against the REAL source — never imported or executed: importing the server
needs the ``mcp`` package and a live session context, and the A4 scan blocks dynamic code
in a test. What is asserted:

  * ONE shared closer carries the UPDATE, so the release-first paths cannot drift apart
    again the way they did (one branch closed the row, another released the lock and never
    looked at it);
  * the closer is failure-tolerant — its connection is closed in a ``finally``, so an
    UPDATE that raises can neither leak the connection nor skip the caller's release;
  * the findings path closes the cycle BEFORE dropping the lock, and REFUSES to release
    when the lock names no session (a process-scoped fallback would free a peer's lock).
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
CLOSER = "_close_cycle_unscored"
UPDATE_MARKER = "SET decision='MOVE_ON', unscored_reason=?"


def _source():
    assert SRC.exists(), f"governance MCP source not found: {SRC}"
    return SRC.read_text()


def _fn_source(name):
    src = _source()
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


RELEASE_PATHS = (
    ("_release_lock_after_metadata_refusal",
     lambda: _fn_source("_release_lock_after_metadata_refusal")),
    ("_release_after_refusal", lambda: _fn_source("_release_after_refusal")),
    ("_advance_task_state[blocked]", _blocked_branch),
)


def test_no_release_path_carries_its_own_copy_of_the_closing_update():
    """ONE implementation, or the copies drift again — which is exactly how this bug happened.

    The orphan-cycle reaper keeps its own UPDATE on purpose: it selects rows that already
    have no live lock, so it needs neither the PENDING guard nor a session to release.
    What must not come back is a release path closing the row itself.
    """
    src = _source()
    assert f"def {CLOSER}(" in src, f"{CLOSER} not defined"
    assert UPDATE_MARKER in _fn_source(CLOSER), "the shared closer must carry the UPDATE"

    for name, fn in RELEASE_PATHS:
        body = fn()
        assert UPDATE_MARKER not in body, (
            f"{name} closes the cycle inline — the release paths must delegate to "
            f"{CLOSER} so they cannot drift apart again"
        )


def test_the_shared_closer_closes_only_a_live_pending_row_and_never_leaks_its_connection():
    body = _fn_source(CLOSER)

    # Resolved, not judged: MOVE_ON so no consumer reads it as pending, and the UPDATE
    # touches only a still-PENDING, non-overridden row — a scored or overridden cycle is
    # never rewritten by a cleanup path.
    assert "decision='MOVE_ON'" in body
    assert "unscored_reason=?" in body
    assert "decision='PENDING' AND user_overrode IS NULL" in body

    # try/finally with the close in the finally: the blocked branch used to close the
    # connection only on the happy path, so an UPDATE that raised leaked it.
    assert "finally:" in body
    assert "conn.close()" in body
    assert body.index("finally:") < body.index("conn.close()"), (
        "the connection must be closed in a finally block, not on the happy path only"
    )
    # The closer reports failure instead of raising, so its caller's release still runs.
    assert "except Exception" in body
    assert "return False" in body
    # ...and it reports SUCCESS honestly: the PENDING/overridden guard means a valid call
    # can match no row, so a bare True there would claim "closed" about a cycle still open.
    assert "rowcount" in body, (
        "the closer must report what the guarded UPDATE actually matched"
    )


def test_findings_refusal_closes_the_cycle_before_releasing_the_lock():
    body = _fn_source("_release_after_refusal")
    assert f"{CLOSER}(" in body, (
        "the findings refusal releases the lock — it must close the PENDING cycle too, "
        "or the released lock leaves a doctor-FAIL orphan for every agent on the host"
    )
    assert body.index(f"{CLOSER}(") < body.index('_release_lock({"session_id"'), (
        "order is load-bearing: closing the cycle AFTER the release leaves a window "
        "where a released lock sits beside an unresolved PENDING cycle"
    )


def test_findings_refusal_refuses_to_guess_which_session_to_release():
    """No session id on the lock → do NOT release, and do NOT close the cycle.

    Closing it while the lock stays held would strand the session: end_change's own
    resolve step would then find no PENDING cycle to close when it retries.
    """
    body = _fn_source("_release_after_refusal")
    assert "(lock or {}).get(\"session_id\")" in body
    assert "if not owner:" in body, "a lock with no session_id must refuse to release"

    i_guard = body.index("if not owner:")
    i_close = body.index(f"{CLOSER}(")
    assert i_guard < i_close, (
        "the owner guard must come BEFORE the cycle close: with no owner there is no "
        "release, and closing the row would leave nothing for the retry to close"
    )
    # The old guessing form passed None (a process-scoped id) — it must be gone.
    assert "_release_lock(None)" not in body
    assert 'if sid else None' not in body


def test_every_release_first_path_uses_the_shared_closer():
    """Metadata refusal, findings refusal, blocked transition — all three."""
    for name, fn in RELEASE_PATHS:
        body = fn()
        assert f"{CLOSER}(" in body, f"{name} releases the lock without closing its cycle"
