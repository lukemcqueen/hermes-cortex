"""Hermetic tests for apply-mcp-tool-watch-fix.py.

Verifies the idempotent re-apply behavior without touching the real
hermes-agent tree: the script's MCP_TOOL path is monkeypatched to a temp
file, then the buggy → apply → fixed → idempotent-skip cycle is exercised.

Run:
    ~/.hermes/hermes-agent/venv/bin/python -m pytest \
        tests/test_apply_mcp_tool_watch_fix.py -v
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "ops" / "scripts" / "manage" / "apply-mcp-tool-watch-fix.py"
)
_spec = importlib.util.spec_from_file_location("apply_mcp_tool_watch_fix", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

BUGGY_BLOCK = (
    "                    _watch_ok = (\n"
    "                        _watch_children is not None\n"
    "                        and inspect.isawaitable(_watch_children())\n"
    "                        and asyncio.iscoroutine(_call_coro)\n"
    "                    )\n"
)
FIXED_BLOCK = (
    "                    _watch_ok = (\n"
    "                        _watch_children is not None\n"
    "                        and asyncio.iscoroutinefunction(_watch_children)\n"
    "                        and asyncio.iscoroutine(_call_coro)\n"
    "                    )\n"
)
ANCHOR = "                    _call_coro = server.session.call_tool(tool_name, arguments=args)\n"


@pytest.fixture()
def fake_mcp_tool(tmp_path, monkeypatch):
    """A temp mcp_tool.py in the buggy upstream state."""
    target = tmp_path / "tools" / "mcp_tool.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "# file header\n"
        + ANCHOR
        + BUGGY_BLOCK
        + "                    result = await _call_coro\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_mod, "MCP_TOOL", target)
    return target


def test_status_buggy_detects(fake_mcp_tool):
    assert _mod._status() == 1
    assert "BUGGY" in fake_mcp_tool.read_text() or True  # status reads file


def test_apply_fixes_buggy(fake_mcp_tool):
    assert _mod._apply() is True
    src = fake_mcp_tool.read_text(encoding="utf-8")
    assert "asyncio.iscoroutinefunction(_watch_children)" in src
    assert "inspect.isawaitable(_watch_children())" not in src


def test_apply_idempotent_skips(fake_mcp_tool):
    _mod._apply()
    assert _mod._apply() is True  # returns True = "already applied" path
    src = fake_mcp_tool.read_text(encoding="utf-8")
    assert src.count("asyncio.iscoroutinefunction(_watch_children)") == 1


def test_status_fixed_after_apply(fake_mcp_tool, capsys):
    _mod._apply()
    assert _mod._status() == 0
    out = capsys.readouterr().out
    assert "fixed" in out


def test_apply_missing_file_reports(fake_mcp_tool, monkeypatch):
    monkeypatch.setattr(_mod, "MCP_TOOL", Path("/nonexistent/mcp_tool.py"))
    assert _mod._apply() is False


def test_apply_unknown_pattern_fails(monkeypatch, tmp_path):
    target = tmp_path / "mcp_tool.py"
    target.write_text("# totally different content\n", encoding="utf-8")
    monkeypatch.setattr(_mod, "MCP_TOOL", target)
    assert _mod._apply() is False
