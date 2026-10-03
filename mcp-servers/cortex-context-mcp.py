#!/usr/bin/env python3
"""
cortex-context-mcp.py — MCP access layer for the cortex context store (S2c).

Thin transport wrapper. The tool surface lives in
`ops/services/mycortex-mem/context_tools.py` and is shared with the CLI
(`ops/scripts/cortex-context.py`), because a harness picks an ACCESS LAYER —
it does not get its own semantics.

Which harness uses which layer:

    MCP  (this file, `hermes mcp add`)   Hermes, Claude Code, Codex
    CLI  (`cortex-context <tool> <json>`) Pi — whose extension API is hooks +
         registerTool, NOT an MCP client

Design: docs/design/cortex-memory-session-mcp.md

Usage:
    hermes mcp add cortex-context \
        --command ~/.hermes/hermes-agent/venv/bin/python3 \
        --args ~/hermes-cortex/mcp-servers/cortex-context-mcp.py

Env (optional; set once per session):
    CORTEX_SESSION_HARNESS / _REPO / _BRANCH / _KEY
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import traceback
from pathlib import Path

if importlib.util.find_spec("mcp") is None:
    print("[cortex-context-mcp] ERROR: 'mcp' package not found. Install: pip install mcp "
          "(or use the Hermes venv python).", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="[cortex-context-mcp] %(levelname)s: %(message)s")

def _find_tools_py():
    """Locate the shared contract from EITHER layout.

    repo:     <repo>/mcp-servers/cortex-context-mcp.py
              -> <repo>/ops/services/mycortex-mem/context_tools.py
    deployed: <deploy>/scripts/cortex-context-mcp.py   (cortex-update.sh flattens
              mcp-servers/ into scripts/)
              -> <deploy>/services/mycortex-mem/context_tools.py

    This used to hard-code the repo-relative path, so the DEPLOYED copy could
    never start ("context_tools.py not found at .../ops/services/..."): the
    deploy maps ops/services/ to <deploy>/services/, dropping the "ops". A
    registered server that cannot start is a wiring that exists and does nothing.
    """
    root = Path(__file__).resolve().parent.parent
    for rel in (Path("ops") / "services" / "mycortex-mem" / "context_tools.py",
                Path("services") / "mycortex-mem" / "context_tools.py"):
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


_TOOLS_PY = _find_tools_py()
if _TOOLS_PY is None:
    _root = Path(__file__).resolve().parent.parent
    print(f"[cortex-context-mcp] ERROR: context_tools.py not found under {_root} "
          "(looked for ops/services/mycortex-mem/ and services/mycortex-mem/). "
          "Run cortex-update.sh, or point --args at the repo copy.",
          file=sys.stderr)
    sys.exit(1)
_spec = importlib.util.spec_from_file_location("cortex_context_tools", _TOOLS_PY)
if _spec is None or _spec.loader is None:
    print(f"[cortex-context-mcp] ERROR: cannot load context_tools.py from {_TOOLS_PY}", file=sys.stderr)
    sys.exit(1)
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool  # noqa: E402


def _result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


async def list_tools(ctx, params=None) -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(name=t["name"], description=t["description"],
             input_schema=tools.tool_schema_for_mcp(t))
        for t in tools.TOOLS
    ])


async def call_tool(ctx, params=None) -> CallToolResult:
    name = params.name if params else ""
    args = (params.arguments or {}) if params else {}
    # dispatch() never raises and never reports a memory outage as a tool error:
    # an unreachable store returns the fail-open message a harness can ignore.
    return _result(tools.dispatch(name, args))


server = Server("cortex-context-mcp", on_list_tools=list_tools, on_call_tool=call_tool)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
