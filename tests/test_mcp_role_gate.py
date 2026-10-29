"""Hermetic test for the CORTEX_MCP_ROLE gate on mcp-servers/loop-gov-mcp.py.

Drives the REAL binary (importing it from the repo path) under each role and
asserts the exposed tool surface — review lists exactly the 7 no-lock-authority
tools, loop-governance lists the complement (lock lifecycle + scoring + task
state), and NO role lists the full set. The partition is DERIVED from the
binary's own full tool list, not a hand-maintained copy, so it cannot drift from
call_tool's real dispatch surface.

Runnable two ways:
  python3 tests/test_mcp_role_gate.py    # standalone (no pytest needed)
  python3 -m pytest tests/test_mcp_role_gate.py  # under pytest
No live store is touched (list_tools / call_tool role path only inspects names).
"""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_role_test", SRC)
assert _spec and _spec.loader, "loop-gov-mcp.py not resolvable"
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

REVIEW_EXPECT = {
    "rereview_change", "cycle_query", "cycle_stats",
    "feedback_accept", "feedback_override",
    "cache_search", "session_identity",
}


class _role_ctx:
    """Context manager overriding CORTEX_MCP_ROLE, restored on exit."""

    def __init__(self, role):
        self.role = role
        self.saved = os.environ.get("CORTEX_MCP_ROLE")

    def __enter__(self):
        if self.role is None:
            os.environ.pop("CORTEX_MCP_ROLE", None)
        else:
            os.environ["CORTEX_MCP_ROLE"] = self.role

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop("CORTEX_MCP_ROLE", None)
        else:
            os.environ["CORTEX_MCP_ROLE"] = self.saved


def _full_names() -> set:
    res = asyncio.run(mod._list_all_tools(None, None))
    return {t.name for t in (res.tools or [])}


def _listed(role: str) -> set:
    with _role_ctx(role):
        res = asyncio.run(mod.list_tools(None, None))
        return {t.name for t in (res.tools or [])}


def test_review_tools_set_is_exactly_seven():
    assert len(REVIEW_EXPECT) == 7
    assert mod.REVIEW_TOOLS == REVIEW_EXPECT


def test_no_role_lists_full_set():
    with _role_ctx(None):
        full = _full_names()
        for n in full:
            assert mod._role_allows(n) is True
        assert len(full) >= 13  # known dispatch surface


def test_review_role_lists_only_the_seven():
    with _role_ctx("review"):
        assert _listed("review") == REVIEW_EXPECT
        for n in _full_names() - REVIEW_EXPECT:
            assert mod._role_allows(n) is False


def test_loop_governance_role_is_the_complement():
    with _role_ctx("loop-governance"):
        full = _full_names()
        assert _listed("loop-governance") == (full - REVIEW_EXPECT)
        assert REVIEW_EXPECT.isdisjoint(_listed("loop-governance"))


def test_unknown_role_fails_open():
    with _role_ctx("nonsense"):
        full = _full_names()
        assert all(mod._role_allows(n) for n in full)


def test_call_tool_refuses_out_of_role_tool():
    class P:  # minimal params stand-in
        name = "begin_change"
        arguments = {}
    with _role_ctx("review"):
        res = asyncio.run(mod.call_tool(None, P()))
        text = "".join(c.text for c in res.content)
        assert "not exposed" in text


_TESTS = [v for k, v in list(globals().items())
          if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    fails = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(_TESTS) - fails}/{len(_TESTS)} passed")
    sys.exit(1 if fails else 0)
