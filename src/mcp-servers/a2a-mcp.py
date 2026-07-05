#!/usr/bin/env python3
"""
A2A Bridge MCP Server — agent discovery + cross-server task delegation.

Reads agent registry from:
  1. ~/.hermes-cortex/a2a/agent-registry.json  (A2A-specific registry)
  2. ~/.hermes/state/agent-registry.json        (fallback — existing health registry)

Tools:
    a2a_list_agents   List all known agents with their URLs and roles
    a2a_get_agent     Get details for a specific agent by name
"""

import asyncio
import importlib.util
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

if importlib.util.find_spec("mcp") is None:
    print("[mcp-server] ERROR: Required 'mcp' Python package not found.", file=sys.stderr)
    print(f"[mcp-server]   {sys.executable} -m pip install mcp", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)
log = logging.getLogger("a2a-bridge")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

HOME = Path.home()

# ── Registry paths ──
A2A_REGISTRY = HOME / ".hermes-cortex" / "a2a" / "agent-registry.json"
STATE_REGISTRY = HOME / ".hermes" / "state" / "agent-registry.json"

# ── Server ──
server = Server("a2a-bridge")

def _load_registry() -> dict:
    """Load agent registry from A2A path first, fall back to state path."""
    for path in [A2A_REGISTRY, STATE_REGISTRY]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load %s: %s", path, e)
    log.warning("No agent registry found — checked %s, %s", A2A_REGISTRY, STATE_REGISTRY)
    return {"agents": {}}

def _normalize_agents(registry: dict) -> list[dict]:
    """Extract and normalize agent list from registry."""
    agents = registry.get("agents", {})
    result = []
    for key, entry in agents.items():
        result.append({
            "name": key,
            "display_name": entry.get("name", key.capitalize()),
            "role": entry.get("role", "unknown"),
            "url": entry.get("url", ""),
            "health_url": entry.get("health_url", ""),
            "health_method": entry.get("health_method", "http"),
            "platform": entry.get("platform", "unknown"),
            "accessible": entry.get("accessible", False),
            "agent_card_url": entry.get("agent_card_url", ""),
        })
    return sorted(result, key=lambda a: a["name"])

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="a2a_list_agents",
            description="List all known agents with their URLs, roles, and accessibility status.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="a2a_get_agent",
            description="Get details for a specific agent by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Agent name (e.g. 'esther', 'joseph')"},
                },
                "required": ["name"],
            },
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
    try:
        if name == "a2a_list_agents":
            return _list_agents()
        elif name == "a2a_get_agent":
            return _get_agent(args.get("name", ""))
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    except Exception as e:
        log.error("Unhandled error in %s: %s", name, e, exc_info=True)
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])

def _list_agents() -> CallToolResult:
    registry = _load_registry()
    agents = _normalize_agents(registry)
    if not agents:
        return CallToolResult(content=[TextContent(type="text", text="No agents found in registry.")])

    lines = [f"📋 {len(agents)} agent(s) in registry:"]
    for a in agents:
        status = "🟢" if a["accessible"] else "🔴"
        role = a["role"]
        url = a["url"] or a["health_url"] or "—"
        lines.append(f"  {status} {a['name']:12s} ({role:22s}) {url}")

    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])

def _get_agent(name: str) -> CallToolResult:
    if not name:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'name' is required.")])

    registry = _load_registry()
    agents = registry.get("agents", {})
    entry = agents.get(name)
    if not entry:
        return CallToolResult(content=[TextContent(type="text", text=f"Agent '{name}' not found in registry.")])

    data = {
        "name": name,
        "display_name": entry.get("name", name.capitalize()),
        "role": entry.get("role", "unknown"),
        "url": entry.get("url", ""),
        "health_url": entry.get("health_url", ""),
        "health_method": entry.get("health_method", "http"),
        "platform": entry.get("platform", "unknown"),
        "accessible": entry.get("accessible", False),
        "is_server": entry.get("is_server", False),
        "is_orchestrator": entry.get("is_orchestrator", False),
        "agent_card_url": entry.get("agent_card_url", ""),
        "inbox_user": entry.get("inbox_user", name),
        "description": entry.get("description", ""),
    }
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data, indent=2))])

# ── Main ──
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
