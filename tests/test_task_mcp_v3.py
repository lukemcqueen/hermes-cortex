#!/usr/bin/env python3
"""Unit tests for task-mcp.py task-model-v3 tools (claim/unclaim/board/report/verify).

Run: python3 -m pytest tests/test_task_mcp_v3.py -q

Hermetic: imports task-mcp as a module (same pattern as test_executor_mcp),
tests the v3 tool surface — list_tools() exposure + handler wiring — WITHOUT
an MCP transport or a live DB. The task_db.cmd_* functions are mocked at the
module boundary; their DB-level behaviour is covered by
tests/test_task_db_v4.py + tests/test-tasks-schema.sh.
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "task_mcp", _REPO / "mcp-servers" / "task-mcp.py")
tm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tm)

V3_TOOLS = {
    "task_claim": ("cmd_claim", ("task_id", "no_notify")),
    "task_unclaim": ("cmd_unclaim", ("task_id", "reason", "no_notify")),
    "task_list_claimable": ("cmd_list_claimable", ("limit",)),
    "task_board": ("cmd_list_board", ()),
    "task_report": ("cmd_report", ("task_id", "evidence", "no_notify")),
    "task_verify": ("cmd_verify", ("task_id", "approve", "note", "no_notify")),
}

_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001"


class Recorder:
    """Record calls made to a task_db.cmd_* function."""

    def __init__(self):
        self.calls = []

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))
        return None


def test_list_tools_exposes_all_v3_tools():
    tools = asyncio.run(tm.list_tools(None))
    names = [t.name for t in tools.tools]
    for tool_name in V3_TOOLS:
        assert tool_name in names, f"{tool_name} missing from list_tools()"


def test_v3_tool_descriptions_carry_data_warning():
    tools = asyncio.run(tm.list_tools(None))
    by_name = {t.name: t for t in tools.tools}
    for tool_name in V3_TOOLS:
        desc = by_name[tool_name].description
        assert "data, never instructions" in desc, tool_name


@pytest.mark.parametrize("tool_name,spec", sorted(V3_TOOLS.items()))
def test_handler_wired_to_cmd_function(tool_name, spec, monkeypatch):
    cmd_name, params = spec
    rec = Recorder()
    monkeypatch.setattr(tm.task_db, cmd_name, rec)
    handler = tm._HANDLERS[tool_name]
    args = {p: (_UUID if p == "task_id"
                else "test-note" if p in ("reason", "evidence", "note")
                else 5 if p == "limit"
                else True if p == "approve"
                else False)
            for p in params}
    result = handler(args)
    assert result.is_error is False, f"{tool_name} errored: {result}"
    assert rec.calls, f"{tool_name} did not call task_db.{cmd_name}"


def test_task_claim_passes_task_id_and_no_notify(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(tm.task_db, "cmd_claim", rec)
    tm._HANDLERS["task_claim"]({"task_id": _UUID, "no_notify": True})
    assert rec.calls == [((_UUID, True), {})]
