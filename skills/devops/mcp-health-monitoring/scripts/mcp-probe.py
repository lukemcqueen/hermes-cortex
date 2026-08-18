#!/usr/bin/env python3
"""mcp-probe.py — import + list_tools health probe for an MCP server.

Usage:  <server-python> mcp-probe.py <server-path>
        e.g. ~/.hermes/hermes-agent/venv/bin/python3 mcp-probe.py \
             ~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py

Prints a JSON array of tool names on success (exit 0); on import crash or
handler failure prints the traceback to stderr and exits non-zero.

Catches the 2026-08-18 failure class (server crashes at import, e.g.
mcp SDK 2.0 removed the decorator API) without a full stdio handshake.

Requires the server to expose a module-level
`async def list_tools(ctx, params=None)` (mcp 2.0 constructor-API shape)
and guard `main()` behind `if __name__ == "__main__":`.

Pitfalls handled by the CALLER, not here:
  - Run with the server's real HOME and cwd=$HOME (servers resolve
    ~/hermes-* paths via Path.home() at import; a foreign HOME false-fails).
  - Run with the server's OWN configured python (the config.yaml `command`),
    so SDK drift in that interpreter is what the probe measures.
"""

import asyncio
import importlib.util
import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: mcp-probe.py <server-path>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    spec = importlib.util.spec_from_file_location("_mcp_probe", path)
    if spec is None or spec.loader is None:
        print(f"cannot load module spec for {path}", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # import crash raises here -> traceback

    async def _run():
        result = await module.list_tools(None, None)
        tools = getattr(result, "tools", result)
        print(json.dumps([getattr(t, "name", str(t)) for t in tools]))

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
