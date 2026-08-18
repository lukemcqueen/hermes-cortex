---
name: mcp-server-building
description: "Build, test, and debug MCP servers for Hermes Agent — logging, dependency checks, fix hints, and best practices."
version: 1.1.0
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [mcp, mcp-server, logging, debugging, tool-building]
    related_skills: [hermes-agent, repo-organization]
---

# MCP Server Building — Hermes Cortex Standard

> **mcp SDK 2.0 (2026-08-18): the decorator API (`@server.list_tools()` /
> `@server.call_tool()`) was REMOVED.** Register handlers via the
> constructor: `Server(name, on_list_tools=..., on_call_tool=...)`.
> The old decorators crash with `AttributeError: 'Server' object has no
> attribute 'list_tools'` on mcp ≥1.0 (see
> `docs/reference/mcp-sdk-v2-migration.md`). All examples below use the
> 2.0 API. Version pinned in the hermes-agent venv: `mcp==2.0.0`.

This skill covers everything needed to build, debug, and deploy MCP servers that agents install via `hermes mcp add`.

---

## 1. Dependency Auto-Check Template

Every MCP server MUST verify the `mcp` package is available at startup and offer a clear fix hint when it's not. Use this at the top of every MCP server:

```python
#!/usr/bin/env python3
"""MCP server template with dependency checking, logging, and error hints."""

import sys
import subprocess
import importlib.util

# ── Dependency Auto-Check ─────────────────────────────────────
_MCP_SPEC = importlib.util.find_spec("mcp")
if _MCP_SPEC is None:
    print("[mcp-server] ERROR: 'mcp' package not found.", file=sys.stderr)
    print("[mcp-server] Install it:", file=sys.stderr)
    print("[mcp-server]   pip install mcp", file=sys.stderr)
    print("[mcp-server] Or if using Hermes venv:", file=sys.stderr)
    print(f"[mcp-server]   {sys.executable} -m pip install mcp", file=sys.stderr)
    sys.exit(1)
```

---

## 2. Comprehensive Logging

Use Python's `logging` module for structured logs. Log to stderr (stdout is reserved for MCP JSON-RPC messages). Never use `print()` for debug info — Hermes captures stderr from MCP server subprocesses.

```python
import logging
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format="[mcp-server] %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
log = logging.getLogger("my-server")
```

**Log levels to use:**

| Level | When |
|-------|------|
| `log.debug(...)` | Detailed info during development |
| `log.info(...)` | Startup, tool calls, successful operations |
| `log.warning(...)` | Recoverable issues (e.g., file not found, retry) |
| `log.error(...)` | Operation failures (e.g., database error) |
| `log.critical(...)` | Server cannot continue (e.g., port in use) |

---

## 3. Guarded Main Entry Point

Every MCP server MUST wrap `asyncio.run(main())` in try/except with full traceback to stderr:

```python
import asyncio
import traceback

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
```

Without this, Hermes sees "Connection closed" with no context when the server crashes.

---

## 4. Tool-Level Error Handling

Every tool handler should catch errors and return a user-friendly `CallToolResult` with the error message and fix hint:

```python
async def call_tool(ctx, params=None) -> CallToolResult:
    name = params.name if params else ""
    args = (params.arguments or {}) if params else {}
    try:
        handlers = {"my_tool": _my_tool}
        handler = handlers.get(name)
        if handler:
            return handler(args)
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    except FileNotFoundError as e:
        log.error(f"File not found in {name}: {e}")
        return CallToolResult(content=[TextContent(type="text", text=f"File not found: {e}. Check the path and try again.")])
    except PermissionError as e:
        log.error(f"Permission denied in {name}: {e}")
        return CallToolResult(content=[TextContent(type="text", text=f"Permission denied: {e}. Run with appropriate privileges.")])
    except Exception as e:
        log.error(f"Unexpected error in {name}: {e}", exc_info=True)
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {e}")])
```

---

## 5. Tool Schema Best Practices

| Do | Don't |
|----|-------|
| Use `description` on every tool | Leave descriptions empty or vague |
| Use `enum` for constrained string values | Accept arbitrary strings |
| Set `required` for mandatory fields | Make everything optional |
| Use `description` on each property | Let agents guess parameter meaning |
| Limit file reads to reasonable max sizes (e.g., 5 MB) | Accept unbounded file sizes |

```python
Tool(
    name="my_tool",
    description="Clear, one-sentence description of what the tool does.",
    inputSchema={
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string",
                "description": "What this parameter is for, any constraints.",
            },
        },
        "required": ["param_name"],
    },
)
```

---

## 6. Standard Boilerplate Template

The full recommended template structure:

```
#!/usr/bin/env python3
""" 1-2 sentence description of the server. """

# ── Imports ──────────────────────────────────────────────────
import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

# ── Dependency Check ────────────────────────────────────────
import importlib.util
if importlib.util.find_spec("mcp") is None:
    print("ERROR: 'mcp' package not found. Install: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)
log = logging.getLogger("server-name")

# ── Imports that depend on mcp ──────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult, ListToolsResult

# ── Handlers (mcp SDK 2.0 — define BEFORE constructing the Server) ──
async def list_tools(ctx, params=None) -> ListToolsResult:
    return ListToolsResult(tools=[...])

async def call_tool(ctx, params=None) -> CallToolResult:
    name = params.name if params else ""
    args = (params.arguments or {}) if params else {}
    ...

# ── Server ───────────────────────────────────────────────────
# mcp 2.0 registers handlers via constructor kwargs, not decorators.
server = Server("server-name", on_list_tools=list_tools, on_call_tool=call_tool)

# ── Tool Implementations ─────────────────────────────────────
def _my_tool(args: dict) -> CallToolResult:
    ...

# ── Main ─────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
```

---

## 7. Debugging Checklist

When an MCP server fails with "Connection closed":

1. **Check `mcp` is installed:** `python3 -c "import mcp; print(mcp.__version__)"`
2. **Check syntax:** `python3 -c "compile(open('server.py').read(), 'server.py', 'exec'); print('OK')"`
3. **Test the handshake manually:** Run the server and send an `initialize` JSON-RPC message:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | timeout 5 python3 server.py 2>&1 | head -1
   ```
4. **Check stderr for errors:** Run the server directly and look for output on stderr.
5. **Verify `hermes mcp test`:** `hermes mcp test server-name` shows connection and available tools.
6. **Re-register if code changed:** `hermes mcp remove server-name` then re-add fresh — stale config causes "Connection closed".
7. **Use `yes` for interactive prompts:** `yes | hermes mcp add ...` handles all prompts.

---

## 8. Installation Commands

```bash
# Fresh install
yes | hermes mcp add server-name --command python3 --args /path/to/server.py

# Remove old config first (safe even if not installed)
hermes mcp remove server-name 2>/dev/null

# Test
hermes mcp test server-name

# Re-register after code changes
hermes mcp remove server-name 2>/dev/null
yes | hermes mcp add server-name --command python3 --args /path/to/server.py
```

---

## 9. Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection closed` | MCP package missing | `pip install mcp` |
| `Connection closed` | Stale config | `hermes mcp remove` then re-add |
| `Connection closed` | Import error in server | Run `python3 server.py` directly, check stderr |
| `Connection closed` | Wrong Python interpreter | Use `--command /path/to/python3` instead of just `python3` |
| `AttributeError: 'Server' object has no attribute 'list_tools'` | mcp SDK ≥1.0 removed the `@server.list_tools()` / `@server.call_tool()` decorators | Use the 2.0 constructor API: `Server(name, on_list_tools=..., on_call_tool=...)`. See `docs/reference/mcp-sdk-v2-migration.md` |
| `ModuleNotFoundError` | Missing dependency | Install the missing package |
| `Permission denied` | File not executable | `chmod +x server.py` |
| `Tool not found` | Wrong tool name in call | Check `hermes mcp test` output for exact names |
