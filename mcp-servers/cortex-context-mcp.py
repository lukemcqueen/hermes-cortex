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
        --command ~/.hermes-cortex/venv/bin/python3 \
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

# ── cortex_lib bootstrap — IDENTICAL in every MCP server; do not vary. ─────
# cortex_lib/paths.py sits in the scripts dir in BOTH layouts (ops/scripts/
# in-repo, scripts/ deployed), so locate it by that dir rather than by guessing a
# relative depth. Guarded on purpose: the import failure is reported by whichever
# server actually needs the resource, naming what it wanted.
resolve_repo_resource = repo_resource_candidates = None
# cortex_lib sits BESIDE this file in the deployed layout (<deploy>/scripts/cortex_lib/)
# but ONE LEVEL DOWN in the repo (<repo>/ops/scripts/cortex_lib/). Search both: a
# bootstrap that knew only the deployed shape left every server unimportable from the
# repo tree — the running system stayed green while the repo's own tests died at import.
for _p in Path(__file__).resolve().parents:
    if (_p / "cortex_lib" / "paths.py").is_file():
        sys.path.insert(0, str(_p))
        break
    if (_p / "ops" / "scripts" / "cortex_lib" / "paths.py").is_file():
        sys.path.insert(0, str(_p / "ops" / "scripts"))
        break
try:
    from cortex_lib.paths import (  # noqa: E402
        repo_resource_candidates, resolve_repo_resource)
except ImportError:
    pass

_TOOLS_REL = "ops/services/mycortex-mem/context_tools.py"
_TOOLS_PY = resolve_repo_resource(_TOOLS_REL) if resolve_repo_resource else None
if _TOOLS_PY is None:
    _tried = ([str(p) for p in repo_resource_candidates(_TOOLS_REL)]
              if repo_resource_candidates else ["<cortex_lib.paths unavailable>"])
    print(f"[cortex-context-mcp] ERROR: {_TOOLS_REL} not found. Tried: "
          + ", ".join(_tried)
          + " — run cortex-update.sh, or point --args at the repo copy.",
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
