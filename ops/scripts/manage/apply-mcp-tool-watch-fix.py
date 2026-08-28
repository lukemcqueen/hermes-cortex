#!/usr/bin/env python3
"""Re-apply the local mcp_tool.py fast-fail probe fix after hermes updates.

Upstream bug (NousResearch hermes-agent, tools/mcp_tool.py ~6189, present
on origin/main as of 2026-08-28): the #81995 fast-fail guard probes the
stdio child-watcher with ``inspect.isawaitable(_watch_children())`` — which
INVOKES the async function, creating a coroutine that is never awaited or
scheduled. Every MCP call leaks one coroutine:

    RuntimeWarning: coroutine 'MCPServerTask._watch_stdio_children' was
    never awaited

Symptom (Titus 2026-08-28): loop-governance MCP calls return empty/garbled
results, so begin_change never completes and the enforcer blocks all write
tools "even for inspection."

Fix: probe the FUNCTION with asyncio.iscoroutinefunction() instead of
invoking it. The real watcher instance is created once in the fast-fail
branch (asyncio.ensure_future(_watch_children())).

Re-apply: every `hermes update` replaces tools/mcp_tool.py and reverts this
fix. cortex-update.sh runs this script after each deploy (same pattern as
install-cron-cost-tracking.py). Idempotent: SKIPs when the fix is present.

Upstream PR: to be filed once local convergence is verified.

Usage:
    python3 apply-mcp-tool-watch-fix.py            # apply if missing
    python3 apply-mcp-tool-watch-fix.py --status   # report only
    python3 apply-mcp-tool-watch-fix.py --force    # re-apply always
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERMES_AGENT = Path.home() / ".hermes" / "hermes-agent"
MCP_TOOL = HERMES_AGENT / "tools" / "mcp_tool.py"

# The buggy probe (as shipped upstream) and the fixed probe.
BUGGY = (
    "                    _watch_ok = (\n"
    "                        _watch_children is not None\n"
    "                        and inspect.isawaitable(_watch_children())\n"
    "                        and asyncio.iscoroutine(_call_coro)\n"
    "                    )\n"
)
FIXED = (
    "                    _watch_ok = (\n"
    "                        _watch_children is not None\n"
    "                        and asyncio.iscoroutinefunction(_watch_children)\n"
    "                        and asyncio.iscoroutine(_call_coro)\n"
    "                    )\n"
)

# Marker comment inserted with the fix, so --status / idempotency can detect
# "fixed" even if upstream reformats the exact BUGGY text.
FIX_MARKER = "# Local fix: probe _watch_stdio_children as a function, not an invocation (upstream #81995 sibling bug, 2026-08-28)"


def _is_fixed(src: str) -> bool:
    return FIX_MARKER in src or "asyncio.iscoroutinefunction(_watch_children)" in src


def _apply() -> bool:
    if not MCP_TOOL.exists():
        print(f"SKIP: {MCP_TOOL} not found", file=sys.stderr)
        return False
    src = MCP_TOOL.read_text(encoding="utf-8", errors="replace")
    if _is_fixed(src):
        print("SKIP: mcp_tool.py watch-probe fix already applied")
        return True
    if BUGGY not in src:
        print(
            "FAIL: buggy probe pattern not found — upstream may have changed "
            "the surrounding code. Inspect manually.",
            file=sys.stderr,
        )
        return False
    src = src.replace(BUGGY, FIXED, 1)
    # Insert the marker above the fixed block (after the preceding blank line
    # and the _watch_children assignment) for durable detection.
    marker_line = f"                    {FIX_MARKER}\n"
    anchor = "                    _call_coro = server.session.call_tool(tool_name, arguments=args)\n"
    if anchor in src:
        src = src.replace(anchor, anchor + marker_line, 1)
    MCP_TOOL.write_text(src, encoding="utf-8")
    print("APPLIED: mcp_tool.py watch-probe fix (idempotent re-apply ready)")
    return True


def _status() -> int:
    if not MCP_TOOL.exists():
        print("STATUS: mcp_tool.py not found")
        return 2
    src = MCP_TOOL.read_text(encoding="utf-8", errors="replace")
    if _is_fixed(src):
        print("STATUS: fixed (iscoroutinefunction probe)")
        return 0
    if BUGGY in src:
        print("STATUS: BUGGY (isawaitable-invocation probe) — fix needed")
        return 1
    print("STATUS: unknown (probe pattern not matched)")
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-apply mcp_tool.py watch-probe fix")
    ap.add_argument("--status", action="store_true", help="report only")
    ap.add_argument("--force", action="store_true", help="re-apply always")
    args = ap.parse_args(argv)

    if args.status:
        return _status()
    ok = _apply()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
