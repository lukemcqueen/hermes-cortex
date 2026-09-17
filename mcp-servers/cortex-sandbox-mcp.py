#!/usr/bin/env python3.12
"""
Cortex Sandbox MCP Server — exposes disk access control as MCP tools.

Tools:
    sandbox_status     — show current DISK_ACCESS_LEVEL and allowed path
    sandbox_check      — check if a path is allowed for an operation
    sandbox_validate   — validate a path list, returning blocked paths only

Usage:
    hermes mcp add --command python3 --args /path/to/cortex-sandbox-mcp.py cortex-sandbox
"""

import asyncio
import importlib.util
import logging
import sys
import traceback
from pathlib import Path

# ── Dependency Check ─────────────────────────────────────────
_MCP_SPEC = importlib.util.find_spec("mcp")
if _MCP_SPEC is None:
    print("[cortex-sandbox] ERROR: 'mcp' package not found.", file=sys.stderr)
    print("[cortex-sandbox] Install: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[cortex-sandbox] %(levelname)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
log = logging.getLogger("cortex-sandbox")

# ── MCP imports (after dependency check) ────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult, ListToolsResult

# ── Local module ─────────────────────────────────────────────
# Resolve the cortex-sandbox.py module relative to this file's location,
# then fall back to the deployed scripts path.
_SERVER_DIR = Path(__file__).resolve().parent
_SANDBOX_MODULE = _SERVER_DIR.parent / "ops" / "scripts" / "sandbox" / "cortex-sandbox.py"
if not _SANDBOX_MODULE.exists():
    _SANDBOX_MODULE = Path.home() / ".hermes-cortex" / "scripts" / "sandbox" / "cortex-sandbox.py"

if not _SANDBOX_MODULE.exists():
    log.error(f"cortex-sandbox.py not found at {_SANDBOX_MODULE}")
    sys.exit(1)

import importlib.machinery
import importlib.util as iu

_loader = importlib.machinery.SourceFileLoader("cortex_sandbox", str(_SANDBOX_MODULE))
_spec = iu.spec_from_loader("cortex_sandbox", _loader)
_cortex_sandbox = iu.module_from_spec(_spec)
_loader.exec_module(_cortex_sandbox)
SandboxConfig = _cortex_sandbox.SandboxConfig
Sandbox = _cortex_sandbox.Sandbox
SandboxBlocked = _cortex_sandbox.SandboxBlocked
SandboxError = _cortex_sandbox.SandboxError
load_config = _cortex_sandbox.load_config


# ── Tools ────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="sandbox_status",
        description="Report current disk access sandbox configuration: level (full/specific), allowed path, and whether restrictions are active.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="sandbox_check",
        description="Check if a filesystem path is permitted for a given operation under the current sandbox policy.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative filesystem path to check.",
                },
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "execute", "delete"],
                    "description": "The operation to check permission for (default: write).",
                },
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="sandbox_validate",
        description="Validate a list of paths against the sandbox policy. Returns only blocked paths (empty list = all allowed).",
        inputSchema={
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of filesystem paths to validate.",
                },
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "execute", "delete"],
                    "description": "Operation to check (default: write).",
                },
            },
            "required": ["paths"],
        },
    ),
]


# ── Handlers (MCP SDK 2.0 constructor API) ───────────────────

async def list_tools(ctx, params=None) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params=None) -> CallToolResult:
    name = params.name if params else ""
    args = (params.arguments or {}) if params else {}
    try:
        if name == "sandbox_status":
            return _sandbox_status(args)
        elif name == "sandbox_check":
            return _sandbox_check(args)
        elif name == "sandbox_validate":
            return _sandbox_validate(args)
        else:
            return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    except Exception as e:
        log.error(f"Tool '{name}' failed: {e}", exc_info=True)
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {e}")])


# ── Tool Implementations ─────────────────────────────────────

def _sandbox_status(_args: dict) -> CallToolResult:
    import json
    config = load_config()
    sandbox = Sandbox(config)
    data = config.to_dict()
    data["sandbox_available"] = True
    return CallToolResult(content=[TextContent(
        type="text",
        text=json.dumps(data, indent=2)
    )])


def _sandbox_check(args: dict) -> CallToolResult:
    import json
    path = args.get("path", "")
    operation = args.get("operation", "write")

    config = load_config()
    sandbox = Sandbox(config)

    try:
        sandbox.check(path, operation)
        return CallToolResult(content=[TextContent(
            type="text",
            text=json.dumps({"allowed": True, "path": path, "operation": operation})
        )])
    except SandboxBlocked as e:
        return CallToolResult(content=[TextContent(
            type="text",
            text=json.dumps({
                "allowed": False,
                "path": path,
                "operation": operation,
                "reason": str(e),
                "allowed_paths": [str(p) for p in config.allowed_paths],
            })
        )])


def _sandbox_validate(args: dict) -> CallToolResult:
    import json
    paths = args.get("paths", [])
    operation = args.get("operation", "write")

    config = load_config()
    sandbox = Sandbox(config)

    blocked = []
    for p in paths:
        try:
            sandbox.check(p, operation)
        except SandboxBlocked as e:
            blocked.append({"path": p, "reason": str(e)})

    return CallToolResult(content=[TextContent(
        type="text",
        text=json.dumps({
            "checked": len(paths),
            "blocked": len(blocked),
            "operation": operation,
            "blocked_paths": blocked,
        }, indent=2)
    )])


# ── Server ───────────────────────────────────────────────────

server = Server("cortex-sandbox", on_list_tools=list_tools, on_call_tool=call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
