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
    unscored, recording a reason an auditor can recompute;
  * work refusals (findings / reviewer unavailable / template missing) keep the lock,
    because only a re-review may clear a verdict about the change.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
HELPER = "_release_lock_after_metadata_refusal"
METADATA_VERDICTS = ("WRONG_REPO", "NO_REPO")


def _source():
    assert SRC.exists(), f"governance MCP source not found: {SRC}"
    return SRC.read_text()


def _helper_source():
    src = _source()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == HELPER:
            segment = ast.get_source_segment(src, node)
            assert segment, f"could not read the source of {HELPER}"
            return segment
    raise AssertionError(f"{HELPER} not found in {SRC}")


def test_helper_resolves_the_cycle_unscored_then_releases_the_lock():
    body = _helper_source()

    # Resolved, not judged: MOVE_ON so no consumer mistakes it for a pending cycle,
    # unscored_reason carrying the facts, and only ever applied to a still-PENDING,
    # non-overridden row.
    assert "decision='MOVE_ON'" in body
    assert "unscored_reason=?" in body
    assert "decision='PENDING'" in body
    assert "user_overrode IS NULL" in body

    # The reason must say that nothing was reviewed — no receipt exists on this path,
    # so nothing is authorised and nothing becomes pushable.
    assert "no receipt" in body

    # Released by the LOCK'S OWN session id, never an env-derived one: the server is a
    # single process shared by every Hermes session, so a wrong id frees a peer's lock
    # or none at all.
    assert '_release_lock({"session_id"' in body
    assert '(state or {}).get("session_id")' in body

    # Order matters: the cycle is resolved before the lock is dropped, so a crash
    # between the two never leaves a released lock beside an unresolved cycle.
    assert body.index("decision='MOVE_ON'") < body.index('_release_lock({"session_id"')


def test_lock_release_is_attempted_even_when_the_cycle_cannot_be_resolved():
    """A dead DB must not leave the lock held — that is the dead-end being fixed.

    The DB-only try/except reports and continues; the release must sit AFTER it (i.e.
    outside that guard) so the failure path still frees the session.
    """
    body = _helper_source()
    i_db_failure = body.index("DB unavailable")
    i_release = body.index('_release_lock({"session_id"')
    assert i_db_failure < i_release, (
        "the cycle-resolution failure path must not skip the lock release"
    )


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
