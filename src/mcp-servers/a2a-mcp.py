#!/usr/bin/env python3
"""
A2A Bridge MCP Server — agent discovery + cross-server task delegation.

Reads agent registry from:
  1. ~/.hermes-cortex/a2a/agent-registry.json  (A2A-specific registry)
  2. ~/.hermes/state/agent-registry.json        (fallback — existing health registry)

Tools:
    a2a_list_agents    List all known agents with URLs and roles
    a2a_get_agent      Get details for a specific agent by name
    a2a_discover       Fetch a remote agent's Agent Card
    a2a_send_task      Submit a task to a remote agent
    a2a_get_task       Poll task status on a remote agent
    a2a_cancel_task    Cancel a pending task on a remote agent
"""

import asyncio
import importlib.util
import json
import logging
import os
import ssl
import sys
import traceback
import urllib.error
import urllib.request
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

# ── mTLS client cert ──
CERT_DIR = HOME / ".hermes-cortex" / "certs"
CLIENT_CERT = CERT_DIR / "hermes-mcp-client.crt"
CLIENT_KEY = CERT_DIR / "hermes-mcp-client.key"

_SSL_CONTEXT = None
if CLIENT_CERT.exists() and CLIENT_KEY.exists():
    try:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.load_cert_chain(str(CLIENT_CERT), str(CLIENT_KEY))
        _SSL_CONTEXT = ctx
        log.info("Loaded mTLS client cert from %s", CLIENT_CERT)
    except Exception as e:
        log.warning("Failed to load mTLS client cert: %s", e)

# ── Server ──
server = Server("a2a-bridge")

# ── Registry helpers ──

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

def _resolve_agent_url(agent_name: str) -> str | None:
    """Resolve an agent's base URL from the registry. Returns None if not found."""
    registry = _load_registry()
    entry = registry.get("agents", {}).get(agent_name)
    if not entry:
        return None
    return entry.get("url") or entry.get("health_url", "").replace("/health", "") or None

# ── HTTP helpers (with mTLS) ──

def _http_get(url: str, timeout: int = 10) -> tuple[int, str]:
    """Make an HTTPS GET request with optional mTLS client cert."""
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, body
    except Exception as e:
        return 0, str(e)

def _http_post(url: str, data: bytes, timeout: int = 15) -> tuple[int, str]:
    """Make an HTTPS POST request with JSON body and optional mTLS client cert."""
    try:
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, body
    except Exception as e:
        return 0, str(e)


# ── Tools ──

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
        Tool(
            name="a2a_discover",
            description="Fetch a remote agent's Agent Card to see their capabilities and skills.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name to discover"},
                },
                "required": ["agent"],
            },
        ),
        Tool(
            name="a2a_send_task",
            description="Submit a task to a remote agent. Returns task ID for status polling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Target agent name"},
                    "description": {"type": "string", "description": "Task description"},
                    "priority": {"type": "string", "enum": ["normal", "urgent", "critical"],
                                 "description": "Task priority", "default": "normal"},
                },
                "required": ["agent", "description"],
            },
        ),
        Tool(
            name="a2a_get_task",
            description="Poll the status of a task on a remote agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name the task was sent to"},
                    "task_id": {"type": "string", "description": "Task ID from a2a_send_task"},
                },
                "required": ["agent", "task_id"],
            },
        ),
        Tool(
            name="a2a_cancel_task",
            description="Cancel a pending task on a remote agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name the task was sent to"},
                    "task_id": {"type": "string", "description": "Task ID to cancel"},
                },
                "required": ["agent", "task_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
    try:
        handlers = {
            "a2a_list_agents": lambda: _list_agents(),
            "a2a_get_agent": lambda: _get_agent(args.get("name", "")),
            "a2a_discover": lambda: _discover(args.get("agent", "")),
            "a2a_send_task": lambda: _send_task(
                args.get("agent", ""), args.get("description", ""), args.get("priority", "normal"),
            ),
            "a2a_get_task": lambda: _get_task(args.get("agent", ""), args.get("task_id", "")),
            "a2a_cancel_task": lambda: _cancel_task(args.get("agent", ""), args.get("task_id", "")),
        }
        handler = handlers.get(name)
        if handler:
            return handler()
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    except Exception as e:
        log.error("Unhandled error in %s: %s", name, e, exc_info=True)
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])


# ── Tool implementations ──

def _list_agents() -> CallToolResult:
    registry = _load_registry()
    agents = _normalize_agents(registry)
    if not agents:
        return CallToolResult(content=[TextContent(type="text", text="No agents found in registry.")])

    lines = [f"📋 {len(agents)} agent(s) in registry:"]
    for a in agents:
        status = "🟢" if a.get("accessible") else "🔴"
        role = a.get("role", "?")
        url = a.get("url") or a.get("health_url") or "—"
        lines.append(f"  {status} {a['name']:12s} ({role:22s}) {url}")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


def _get_agent(name: str) -> CallToolResult:
    if not name:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'name' is required.")])
    registry = _load_registry()
    entry = registry.get("agents", {}).get(name)
    if not entry:
        return CallToolResult(content=[TextContent(type="text", text=f"Agent '{name}' not found in registry.")])
    data = {
        "name": name, "display_name": entry.get("name", name.capitalize()),
        "role": entry.get("role", "unknown"), "url": entry.get("url", ""),
        "health_url": entry.get("health_url", ""), "platform": entry.get("platform", "unknown"),
        "accessible": entry.get("accessible", False),
        "is_server": entry.get("is_server", False),
        "agent_card_url": entry.get("agent_card_url", ""),
        "description": entry.get("description", ""),
    }
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data, indent=2))])


def _discover(agent: str) -> CallToolResult:
    """Fetch a remote agent's Agent Card."""
    if not agent:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' is required.")])

    # Resolve agent URL
    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Agent '{agent}' not found in registry. Run a2a_list_agents to see available agents."
        )])

    # Try well-known endpoint first, then /a2a/agent-card
    card_urls = [
        f"{base_url.rstrip('/')}/.well-known/agent-card.json",
        f"{base_url.rstrip('/')}/a2a/agent-card",
    ]

    for card_url in card_urls:
        status, body = _http_get(card_url)
        if status == 200:
            try:
                card = json.loads(body)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(card, indent=2))])
            except json.JSONDecodeError:
                return CallToolResult(content=[TextContent(type="text",
                    text=f"Agent Card at {card_url} returned invalid JSON: {body[:200]}")])

    return CallToolResult(content=[TextContent(type="text",
        text=f"Could not fetch Agent Card for '{agent}' — tried {', '.join(card_urls)}. "
             "Ensure the remote agent's A2A server and nginx are running.")])


def _send_task(agent: str, description: str, priority: str = "normal") -> CallToolResult:
    """Submit a task to a remote agent via A2A JSON-RPC."""
    if not agent or not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' and 'description' are required.")])

    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Agent '{agent}' not found in registry.")])

    url = f"{base_url.rstrip('/')}/a2a/task"
    payload = json.dumps({
        "jsonrpc": "2.0", "id": f"hermes-{Path.home().name}",
        "method": "tasks/send",
        "params": {
            "task": {
                "state": "submitted",
                "messages": [{
                    "role": "user",
                    "parts": [{"type": "text", "text": description}],
                }],
            },
        },
    }).encode()

    status_code, body = _http_post(url, payload)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Task submission failed (HTTP {status_code}): {body[:300] if body else 'no response'}")])


def _get_task(agent: str, task_id: str) -> CallToolResult:
    """Poll task status on a remote agent."""
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' and 'task_id' are required.")])

    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(type="text", text=f"Agent '{agent}' not found in registry.")])

    url = f"{base_url.rstrip('/')}/a2a/task/{task_id}"
    status_code, body = _http_get(url)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Task query failed (HTTP {status_code}): {body[:300] if body else 'no response'}" )])


def _cancel_task(agent: str, task_id: str) -> CallToolResult:
    """Cancel a pending task on a remote agent."""
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' and 'task_id' are required.")])

    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(type="text", text=f"Agent '{agent}' not found in registry.")])

    url = f"{base_url.rstrip('/')}/a2a/task/{task_id}/cancel"
    payload = json.dumps({"jsonrpc": "2.0", "id": 1}).encode()
    status_code, body = _http_post(url, payload)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Task cancellation failed (HTTP {status_code}): {body[:300] if body else 'no response'}" )])


# ── Main ──
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
