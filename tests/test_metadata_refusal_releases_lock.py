"""A metadata refusal must FREE the lock; a work refusal must still HOLD it.

Measured 2026-10-14 (reported by a peer): a lock tagged with a repo the session was
not working in made ``end_change`` refuse, and the lock stayed held — so that session
could not start its next change and other sessions could not close their turns.

Releasing the lock ALONE is not enough, and that is the trap this test pins down:
the doctor counts a PENDING cycle as EXPECTED while a non-terminal lock exists, and
as a FAIL (leak) the moment the lock is gone — so a released lock beside an
unresolved cycle blocks the push for EVERY agent on the host. One such row (cycle
12538) was the sole doctor failure behind a refused push on this host.

The assertions below read the REAL source of the governance MCP server rather than
importing or executing it: importing needs the `mcp` package and a live session
context, and a test must not execute extracted code (it is also why this file carries
no exec/compile — the A4 scan blocks that). Both directions are pinned:
  * metadata refusals (WRONG_REPO / NO_REPO) release the lock AND close the cycle
    unscored through the shared closer, recording a reason an auditor can recompute;
  * work refusals (findings / reviewer unavailable / template missing) keep the lock,
    because only a re-review may clear a verdict about the change.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
HELPER = "_release_lock_after_metadata_refusal"
CLOSER = "_close_cycle_unscored"
METADATA_VERDICTS = ("WRONG_REPO", "NO_REPO")


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


def _helper_source():
    return _fn_source(HELPER)


def test_helper_resolves_the_cycle_unscored_then_releases_the_lock():
    body = _helper_source()

    # The closing UPDATE lives in the ONE shared closer (pinned by
    # tests/test_release_after_refusal_closes_cycle.py); this path must DELEGATE to it
    # rather than carry a copy of its own, which is how the copies drifted apart.
    assert f"{CLOSER}(" in body
    # The note it passes must say that nothing was reviewed — no receipt exists on this
    # path, so nothing is authorised and nothing becomes pushable.
    assert "no receipt" in body

    # Released by the LOCK'S OWN session id, never an env-derived one: the server is a
    # single process shared by every Hermes session, so a wrong id frees a peer's lock
    # or none at all.
    assert '_release_lock({"session_id"' in body
    assert '(state or {}).get("session_id")' in body

    # Order matters: the cycle is resolved before the lock is dropped, so a crash
    # between the two never leaves a released lock beside an unresolved cycle.
    assert body.index(f"{CLOSER}(") < body.index('_release_lock({"session_id"')


def test_helper_refuses_to_guess_which_session_to_release():
    """A lock with no session_id must NOT be released by a process-scoped fallback.

    Closing its cycle would be just as wrong: with no session to release it for, the
    row must stay PENDING (the doctor counts that as EXPECTED beside a live lock) or the
    session's own retry finds nothing left to close.
    """
    body = _helper_source()
    assert "if not owner:" in body
    assert body.index("if not owner:") < body.index(f"{CLOSER}("), (
        "the owner guard must come BEFORE the cycle close — no owner means no release, "
        "and closing the row would strand the retry"
    )
    # The old guessing form passed None (a process-scoped id) — it must be gone.
    assert '_release_lock({"session_id": sid} if sid else None)' not in body
    assert "_release_lock(None)" not in body


def test_lock_release_is_attempted_even_when_the_cycle_cannot_be_resolved():
    """A dead store must not leave the lock held — that is the dead-end being fixed.

    The shared closer reports its own failure and never raises, so the release must sit
    AFTER it unconditionally: gating the release on the closer's result would re-create
    the dead-end the closer exists to prevent.
    """
    body = _helper_source()
    assert "if resolved" not in body, "the closer's result must not gate the lock release"
    closer = _fn_source(CLOSER)
    assert "except Exception" in closer, "the closer must report failure, not raise"
    assert "finally:" in closer and "conn.close()" in closer


def test_only_metadata_refusals_release_the_lock():
    """Work refusals must keep the lock; metadata refusals must not — on the real source."""
    lines = _source().splitlines()
    markers = [
        i for i, ln in enumerate(lines)
        if "_mark_close_refused(" in ln and not ln.strip().startswith("def ")
    ]
    assert len(markers) >= 4, f"expected every refusal site to be found, got {markers}"

    checked_meta = 0
    for i in markers:
        window = "\n".join(lines[i:i + 14])
        is_metadata = any(v in lines[i] for v in METADATA_VERDICTS)
        releases = HELPER in window
        assert is_metadata == releases, (
            f"line {i + 1} ({lines[i].strip()}): metadata={is_metadata} but "
            f"releases_lock={releases} — a work refusal must hold the lock, a "
            f"metadata refusal must free it"
        )
        checked_meta += int(is_metadata)

    assert checked_meta == len(METADATA_VERDICTS), f"expected 2 metadata sites, saw {checked_meta}"

    calls = [i for i, ln in enumerate(lines) if HELPER + "(" in ln and "def " not in ln]
    assert len(calls) == len(METADATA_VERDICTS), f"stray release call sites: {calls}"
