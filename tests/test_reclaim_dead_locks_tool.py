"""The reclaim path: an explicit way to END a lock whose owner is provably dead.

Luke 2026-10-14: "a lock whose owner cannot progress should be ended or taken over
rather than left to burn its TTL." The TTL purge already ends dead locks, but it fires
implicitly (on begin_change / startup) with no way to ask "is anything dead right now?"
and no way to act deliberately — a session blocked by a dead peer's lock had no tool.

Pinned here against the REAL source (never imported or executed — importing needs the
`mcp` package and a live session context, and the A4 scan blocks dynamic code in a test):

  * the tool is REGISTERED (tools list + handler dispatch), or calling it is "Unknown tool";
  * it reuses the fleet's ONE staleness predicate (`_is_lock_stale`) instead of writing a
    second age rule — a second rule is how the purge and the reclaim would drift apart and
    start disagreeing about which locks are dead;
  * it is REPORT-ONLY by default: nothing is unlinked unless the caller passed apply=true;
  * it never touches THIS session's own lock, live or not;
  * it closes the dead owner's cycles through the EXISTING orphan resolver, not a second
    copy of the closing SQL.

The behaviour (a dead lock ended, its cycle closed unscored, a fresh peer lock left alone)
is exercised end-to-end by docs/evidence/reclaim-dead-locks-probe.py against a THROWAWAY
state dir, which is where a live-state test would be dangerous.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
TOOL = "reclaim_dead_locks"
HANDLER = "_reclaim_dead_locks"


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


def test_the_tool_is_registered_in_both_places():
    """A tool in the list with no handler answers 'Unknown tool'; a handler with no tool
    entry is unreachable. Both, or the capability does not exist."""
    src = _source()
    assert f'name="{TOOL}"' in src, f"{TOOL} is not in the tools list"
    assert f'"{TOOL}": {HANDLER}' in src, f"{TOOL} is not in the handler dispatch table"
    assert f"def {HANDLER}(" in src, f"{HANDLER} is not defined"


def test_it_reuses_the_one_staleness_predicate():
    """NEVER a second age rule: the purge and the reclaim must not disagree about 'dead'."""
    body = _fn_source(HANDLER)
    assert "_is_lock_stale(" in body, "the reclaim must use the fleet's staleness predicate"
    assert "total_seconds" not in body, (
        "the handler computes its own age rule — that is a second staleness rule, which is "
        "how two callers start disagreeing about which locks are dead"
    )
    # The predicate needs the lock file's mtime as its fallback for malformed heartbeats.
    assert "st_mtime" in body, "pass the lock file's mtime, or a malformed heartbeat pins the lock"


def test_report_only_by_default():
    body = _fn_source(HANDLER)
    assert 'args.get("apply"' in body, "apply must be an explicit opt-in"
    assert "unlink()" in body
    assert 'args.get("apply"' in body and body.index('args.get("apply"') < body.index("unlink()"), (
        "the unlink must sit behind the apply flag: a default call must change nothing"
    )


def test_it_never_touches_this_sessions_own_lock():
    body = _fn_source(HANDLER)
    assert "get_session_id(" in body, "resolve this session's id to exclude its own lock"
    assert "== own" in body or "!= own" in body, (
        "the handler must skip its own session's lock, live or not"
    )


def test_it_closes_cycles_through_the_existing_resolver():
    """No second copy of the closing SQL — the release paths already share ONE closer."""
    body = _fn_source(HANDLER)
    assert "_resolve_orphaned_pending_cycles(" in body
    assert "loop_cycles" not in body, (
        "the reclaim writes its own cycle SQL instead of reusing the orphan resolver"
    )
    assert "decision='MOVE_ON'" not in body, "the closing UPDATE belongs to the shared closer"


def test_the_docstring_says_what_it_is_NOT():
    """The refusal has to be legible from the tool itself: no takeover, no live lock."""
    src = _source()
    start = src.index(f"def {HANDLER}(")
    doc = src[start:src.index('"""', src.index('"""', start) + 3)]
    low = doc.lower()
    assert "take over" in low or "takeover" in low, (
        "say that reclaiming ENDS the lock and does not inherit the dead session's scope"
    )
    assert "live" in low, "say that a live owner's lock is never reclaimed"
