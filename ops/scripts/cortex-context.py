#!/usr/bin/env python3
"""cortex-context — CLI access layer for the cortex context store (S2c).

The harness-facing CLI: Pi's extension API is hooks + `registerTool`, not an MCP
client, so a Pi extension reaches the shared tool surface through this instead
of through MCP. Both layers call ONE implementation
(`ops/services/mycortex-mem/context_tools.py`) — a harness picks an access
layer, it does not get its own semantics.

    cortex-context mem_context '{}'
    cortex-context session_checkpoint '{"done":["x"],"pending":["y"]}'
    cortex-context --list
    cortex-context --tools-json        # machine-readable, for a TS extension

Contracts:
  * **Exit 0 whenever the tool ran** — including "memory unavailable". A harness
    hook or tool call must not fail the harness because memory was unreachable.
    Exit 1 only for a usage error (unknown tool, malformed JSON).
  * Identity comes from CORTEX_SESSION_* env when set, else from git — the same
    precedence the MCP server and the harness trigger use, so a checkpoint
    written here is restorable there.

Design: docs/design/cortex-memory-session-mcp.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_TOOLS_PY = (Path(__file__).resolve().parent.parent.parent
             / "ops" / "services" / "mycortex-mem" / "context_tools.py")
if not _TOOLS_PY.is_file():
    # Deployed layout: ~/.hermes-cortex/scripts/cortex-context.py
    _TOOLS_PY = Path.home() / ".hermes-cortex" / "services" / "mycortex-mem" / "context_tools.py"
if not _TOOLS_PY.is_file():
    print(f"cortex-context: context_tools.py not found (tried repo + deployed) — skipping",
          file=sys.stderr)
    sys.exit(0)

_spec = importlib.util.spec_from_file_location("cortex_context_tools", _TOOLS_PY)
if _spec is None or _spec.loader is None:
    print(f"cortex-context: cannot load {_TOOLS_PY}", file=sys.stderr)
    sys.exit(0)
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="cortex-context",
        description="Memory + session over one store. Emits JSON on stdout.")
    ap.add_argument("tool", nargs="?", help="tool name (mem_* / session_*)")
    ap.add_argument("args", nargs="?", default="{}",
                    help="JSON object of arguments (default: {})")
    ap.add_argument("--list", action="store_true", help="list tool names + descriptions")
    ap.add_argument("--tools-json", action="store_true",
                    help="emit the full tool metadata as JSON (for a harness extension)")
    a = ap.parse_args()

    if a.tools_json:
        print(json.dumps(tools.TOOLS, indent=2, ensure_ascii=False))
        return 0

    if a.list or not a.tool:
        for t in tools.TOOLS:
            print(f"{t['name']:<20} {t['description'].split('.')[0]}")
        return 0

    if a.tool not in tools.HANDLERS:
        print(f"cortex-context: unknown tool '{a.tool}' — try --list", file=sys.stderr)
        return 1

    try:
        payload = json.loads(a.args) if a.args.strip() else {}
    except json.JSONDecodeError as e:
        print(f"cortex-context: arguments must be a JSON object ({e})", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("cortex-context: arguments must be a JSON object", file=sys.stderr)
        return 1

    # dispatch() never raises: an unreachable store yields the fail-open message
    # and this still exits 0, because a harness must carry on.
    print(tools.dispatch(a.tool, payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
