#!/usr/bin/env python3
"""
Agent Bus MCP Server — Hermes Cortex agent messaging + task delegation.

SAME tool interface as the old `inbox-mcp.py` — ZERO agent disruption.
Backend switched to the Agent Bus (Postgres-native PGMQ on port 8903).

PRIMARY: Agent Bus (Bearer token auth)
FALLBACK: Old file-based inbox (Basic auth, port 8903, being deprecated)

Config (options in order of precedence):
  # Primary — Agent Bus
  CORTEX_BUS_URL=https://your-domain.com:13004
  CORTEX_BUS_TOKEN=hbus_...

  # Auth for nginx proxy (Basic auth for agents without tokens)
  CORTEX_BUS_AUTH=agent_name:password

  # Fallback — old inbox (deprecated, remove when full cutover complete)
  CORTEX_BUS_FALLBACK_URL=...
  AGENT_NAME=moses

  Or via ~/.hermes-cortex/cortex-bus.conf (key=value format)
    CORTEX_BUS_URL=https://domain:13004
    CORTEX_BUS_TOKEN=hbus_...

Tools:
  inbox_send         Send message (to agents or 'all')
  inbox_read         Read recent messages (filtered to your agent)
  inbox_watch        Check for new messages
  inbox_delete       Delete/archive a message
  inbox_list_agents  List all known agents
  inbox_get_agent    Get agent details
  inbox_discover     Fetch agent card
  inbox_send_task    Delegate task to another agent (via inbox message)
  inbox_get_task     Find a task by ID in inbox messages
  inbox_cancel_task  Send cancel request for a pending task
"""

import asyncio
import base64
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HOME = Path.home()

# ── Dependency Check ──────────────────────────────────────────
if importlib.util.find_spec("mcp") is None:
    print("[mcp-server] ERROR: Required 'mcp' Python package not found.", file=sys.stderr)
    print(f"[mcp-server]   {sys.executable} -m pip install mcp", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s",
                    stream=sys.stderr, force=True)
log = logging.getLogger("agent-bus-mcp")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult


# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# File config paths
CONFIG_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"
PROXY_PATH = "/usr/local/bin/mcp-inbox-proxy"

# ── Config keys ───────────────────────────────────────────────
# Primary: Bus URL + Bearer token (new)
bus_url = os.environ.get("CORTEX_BUS_URL", "")
bus_token = os.environ.get("CORTEX_BUS_TOKEN", "")

# Primary auth for nginx bus access
bus_auth = os.environ.get("CORTEX_BUS_AUTH", "") or os.environ.get("CORTEX_BASIC_AUTH", "")

# Fallback: old inbox URL (deprecated, use CORTEX_BUS_URL)
fallback_url = os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or os.environ.get("CORTEX_INBOX_URL", "")
fallback_auth = os.environ.get("CORTEX_BUS_AUTH", "") or os.environ.get("CORTEX_INBOX_AUTH", "") or os.environ.get("CORTEX_BASIC_AUTH", "")
agent_name = os.environ.get("AGENT_NAME", "")

# Support MOSES_* prefix (deprecated, remove eventually)
_OLD_ENV_MAP = {
    "MOSES_INBOX_URL": ("CORTEX_BUS_FALLBACK_URL or CORTEX_INBOX_URL", "fallback_url"),
    "MOSES_INBOX_AUTH": ("CORTEX_BUS_AUTH or CORTEX_INBOX_AUTH", "fallback_auth"),
}
for old_key, (new_key, var_name) in _OLD_ENV_MAP.items():
    val = os.environ.get(old_key, "")
    if val and not locals()["fallback_url" if "URL" in old_key else "fallback_auth"]:
        log.warning("⚠️  %s is deprecated — use %s", old_key, new_key)
        if "URL" in old_key:
            fallback_url = val
        else:
            fallback_auth = val

# Parse config file (lower priority than env vars)
if CONFIG_FILE.exists():
    try:
        _KEY_MAP = {
            "CORTEX_BUS_URL": ("bus_url", False),
            "CORTEX_BUS_TOKEN": ("bus_token", False),
            "CORTEX_BUS_AUTH": ("bus_auth", False),
            "CORTEX_BUS_BASIC_AUTH": ("bus_auth", False),
            "CORTEX_BASIC_AUTH": ("bus_auth", True),
            "CORTEX_BUS_FALLBACK_URL": ("fallback_url", False),
            "CORTEX_INBOX_URL": ("fallback_url", True),
            "CORTEX_INBOX_AUTH": ("fallback_auth", True),
            "AGENT_NAME": ("agent_name", False),
            "MOSES_INBOX_URL": ("fallback_url", True),
            "MOSES_INBOX_AUTH": ("fallback_auth", True),
        }
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
            v = re.sub(r"\s+#.*$", "", v).strip()
            if k in _KEY_MAP:
                var_name, is_deprecated = _KEY_MAP[k]
                if not locals()[var_name]:
                    locals()[var_name] = v
                    if is_deprecated:
                        log.warning("⚠️  %s in config is deprecated — use CORTEX_BUS_URL/CORTEX_BUS_TOKEN instead", k)
    except Exception as e:
        log.warning("Failed to read %s: %s", CONFIG_FILE, e)

# ── Agent identity ────────────────────────────────────────────
_auth = bus_auth or fallback_auth
if not agent_name and _auth and ":" in _auth:
    agent_name = _auth.split(":", 1)[0]
if not agent_name:
    agent_name = os.environ.get("USER", "agent")
DEFAULT_AGENT = agent_name

# ── Build endpoint list ───────────────────────────────────────
# NOTE: We try endpoints top-to-bottom. The first one to respond
# with a real HTTP status (not connection error) wins.
# "Connection error" (status=0) cascades to next URL.

_ENDPOINTS = []  # list of (label, base_url, headers_dict)

# 1. Agent Bus — Bearer token preferred, then Basic auth for nginx proxies
if bus_url:
    bus_base = bus_url.rstrip("/").rstrip("send").rstrip("api/inbox").rstrip("/")
    if bus_token:
        _ENDPOINTS.append(("Agent Bus (Bearer)", bus_base, {"Authorization": f"Bearer {bus_token}"}))
    if bus_auth:
        encoded = base64.b64encode(bus_auth.encode()).decode()
        _ENDPOINTS.append(("Agent Bus (Basic)", bus_base, {"Authorization": "Basic " + encoded}))

# 2. Old inbox fallback (deprecated — use CORTEX_BUS_URL)
if fallback_url:
    auth_headers = {}
    if fallback_auth:
        encoded = base64.b64encode(fallback_auth.encode()).decode()
        auth_headers = {"Authorization": "Basic " + encoded}
    _ENDPOINTS.append(("Old Inbox (fallback)", fallback_url, auth_headers))

if not _ENDPOINTS:
    log.warning("⚠️  No bus endpoints configured — set CORTEX_BUS_URL or CORTEX_BUS_FALLBACK_URL")

log.info("Agent Bus MCP — agent=%s  bus=%s", DEFAULT_AGENT,
         bool(bus_url) or "not configured (set CORTEX_BUS_URL)")
log.info("Endpoint chain:")
for name, url, _ in _ENDPOINTS:
    log.info("  %s → %s", name, url)


# ═══════════════════════════════════════════════════════════════
#  HTTP CLIENT
# ═══════════════════════════════════════════════════════════════

def _http_json(endpoint_label: str, base_url: str, headers: dict,
               method: str, path: str, body: dict | None = None,
               timeout: int = 10) -> tuple[int, str, dict]:
    """Send JSON HTTP request to one endpoint. Returns (status, body_text, response_headers_dict)."""
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    log.debug("  → %s: %s %s", endpoint_label, method, url)

    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req_headers.update(headers)
    data = json.dumps(body).encode() if body else None

    # Try proxy first (if available — handles root-owned client certs)
    if Path(PROXY_PATH).exists():
        try:
            payload = json.dumps({
                "url": url, "method": method,
                "data": data.decode() if data else None,
                "headers": req_headers,
            })
            r = subprocess.run(
                ["sudo", "-n", PROXY_PATH], input=payload,
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0 and r.stdout.strip():
                result = json.loads(r.stdout)
                return result.get("status", 0), result.get("body", ""), result.get("headers", {})
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            pass  # Fall through to direct HTTP

    # Direct HTTP
    try:
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:1000]
        return e.code, body, dict(e.headers)
    except Exception as e:
        return 0, str(e), {}


def _request(method: str, path: str, body: dict | None = None,
             cascade_on: set | None = None) -> tuple[int, str]:
    """Try each endpoint in the chain, cascading on connection errors.
    
    Args:
        method: HTTP method (GET, POST, DELETE)
        path: API path (e.g. 'api/pgmq/send')
        body: JSON body for POST requests
        cascade_on: HTTP status codes that should cascade to the next endpoint
                    (default: {401, 403, 404, 502, 503})
    
    Returns:
        (status_code, response_body) from the first successful endpoint.
        (0, error_msg) if all endpoints fail.
    """
    cascade = cascade_on or {401, 403, 404, 502, 503}
    last_error = ""

    for label, base_url, headers in _ENDPOINTS:
        status, resp_body, _ = _http_json(label, base_url, headers, method, path, body)
        if status != 0:
            if status in cascade:
                log.warning("  %s: HTTP %s (cascading)", label, status)
                last_error = f"HTTP {status}"
                continue
            return status, resp_body
        last_error = resp_body
        log.warning("  %s: unreachable (%s)", label, resp_body[:100])

    return 0, f"All endpoints unreachable. Last error: {last_error}"


# ═══════════════════════════════════════════════════════════════
#  MCP SERVER
# ═══════════════════════════════════════════════════════════════

server = Server("agent-bus")

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# ── Tool Definitions ──────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="inbox_send",
            description="Send a message to the agent inbox. Delivered via Agent Bus (PGMQ). Supports optional file attachment (max 5 MB).",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Message subject"},
                    "body": {"type": "string", "description": "Message body"},
                    "to": {"type": "string", "description": "Recipient(s) — agent name or 'all' (default)"},
                    "topic": {"type": "string", "description": "Topic channel (default: general)"},
                    "priority": {"type": "string", "enum": ["normal", "urgent", "critical"], "description": "Priority"},
                    "file_path": {"type": "string", "description": "Optional file to attach (text embedded inline, binary referenced). Max 5 MB."},
                },
                "required": ["subject", "body"],
            },
        ),
        Tool(
            name="inbox_read",
            description="Read recent inbox messages from the Agent Bus. Always filtered to your agent (set via AGENT_NAME in config).",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages (default 10)"},
                    "topic": {"type": "string", "description": "Filter by topic (requires bus support)"},
                    "unread_only": {"type": "boolean", "description": "Only unread/new messages"},
                },
            },
        ),
        Tool(
            name="inbox_watch",
            description="Check for new messages for your agent via the Agent Bus.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent messages to check (default 5)"},
                },
            },
        ),
        Tool(
            name="inbox_delete",
            description="Delete/archive a message from the queue. On the bus, this archives it (moves to archive table). On old inbox, it moves to trash/.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Message filename (e.g. '20260625090000-titus.md') or msg_id (UUID)"},
                },
                "required": ["filename"],
            },
        ),
        Tool(
            name="inbox_list_agents",
            description="List all known agents with their URLs, roles, and accessibility status.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="inbox_get_agent",
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
            name="inbox_discover",
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
            name="inbox_send_task",
            description="Delegate a task to another agent. Sends an inbox message with task_id, description, and priority. The target agent picks it up via inbox_watch.",
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
            name="inbox_get_task",
            description="Find a task by ID in inbox messages. Searches messages from the target agent for a matching task_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name the task was sent to"},
                    "task_id": {"type": "string", "description": "Task ID from inbox_send_task"},
                },
                "required": ["agent", "task_id"],
            },
        ),
        Tool(
            name="inbox_cancel_task",
            description="Send a cancel request for a pending task. Sends a cancel message to the target agent's inbox.",
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
            "inbox_send": _inbox_send, "inbox_read": _inbox_read,
            "inbox_watch": _inbox_watch, "inbox_delete": _inbox_delete,
            "inbox_list_agents": _inbox_list_agents,
            "inbox_get_agent": _inbox_get_agent,
            "inbox_discover": _inbox_discover,
            "inbox_send_task": _inbox_send_task,
            "inbox_get_task": _inbox_get_task,
            "inbox_cancel_task": _inbox_cancel_task,
        }
        handler = handlers.get(name)
        if handler:
            return handler(args)
        return CallToolResult(content=[TextContent(type="text", text="Unknown tool: " + name)])
    except Exception as e:
        log.error("Unhandled error in %s: %s", name, e, exc_info=True)
        return CallToolResult(content=[TextContent(type="text", text="Error: " + str(e))])


# ═══════════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════


def _inbox_send(args: dict) -> CallToolResult:
    """Send a message. Primary: POST to Bus /api/pgmq/send.
    Fallback: POST to old inbox /send endpoint."""
    log.info("inbox_send: to=%s topic=%s", args.get("to"), args.get("topic"))

    body_text = args["body"]
    recipient = args.get("to", "moses")
    topic = args.get("topic", "general")
    priority = args.get("priority", "normal")
    fp_arg = args.get("file_path", "")

    # Attach file to body text
    if fp_arg and fp_arg.strip():
        fpath = Path(fp_arg.strip()).expanduser()
        if not fpath.exists():
            return CallToolResult(content=[TextContent(type="text", text=f"File not found: {fpath}")])
        fsize = fpath.stat().st_size
        if fsize > MAX_FILE_SIZE:
            return CallToolResult(content=[TextContent(type="text", text=f"File too large ({fsize} bytes). Max 5 MB.")])
        try:
            raw = fpath.read_bytes()
            is_text = b"\x00" not in raw[:8192]
            if is_text:
                text = raw.decode("utf-8", errors="replace")
                if len(text) > 50000:
                    text = text[:50000] + "\n... [truncated at 50K chars]"
                body_text += f"\n\n---\n**Attachment: {fpath.name}**\n```\n{text}\n```"
            else:
                body_text += f"\n\n---\n**Attachment: {fpath.name}** ({fsize} bytes, binary)"
        except Exception as e:
            body_text += f"\n\n---\n**Attachment: {fpath.name}** (read error: {e})"

    # 🟢 Try: Bus /api/pgmq/send
    queue_name = f"inbox_{recipient}" if recipient != "all" else "broadcast"
    status, body = _request("POST", "api/pgmq/send", {
        "queue": queue_name,
        "message": {
            "from": DEFAULT_AGENT,
            "to": recipient,
            "topic": topic,
            "subject": args["subject"],
            "body": body_text,
            "priority": priority,
        },
        "priority": {"normal": 0, "urgent": 10, "critical": 20}.get(priority, 0),
    })

    if status == 200:
        fp_tag = f" + {Path(fp_arg.strip()).expanduser().name}" if fp_arg and fp_arg.strip() else ""
        return CallToolResult(content=[TextContent(type="text", text=f"Message sent{fp_tag}.")])

    # 🟡 Fallback: Old inbox /send
    data = urllib.parse.urlencode({
        "from": DEFAULT_AGENT, "to": recipient, "topic": topic,
        "subject": args["subject"], "body": body_text, "priority": priority,
    }).encode()
    for label, base_url, headers in _ENDPOINTS:
        status2, resp2, _ = _http_json(label, base_url, headers, "POST", "send",
                                        None, timeout=10)
        if status2 == 200:
            fp_tag = f" + {Path(fp_arg.strip()).expanduser().name}" if fp_arg and fp_arg.strip() else ""
            return CallToolResult(content=[TextContent(type="text",
                text=f"Message sent via {label}{fp_tag} (bus unavailable).")])
        # Try form-encoded for old inbox
        url = base_url.rstrip("/") + "/send"
        try:
            req = urllib.request.Request(url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded", **headers})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return CallToolResult(content=[TextContent(type="text",
                        text=f"Message sent via {label} fallback.")])
        except urllib.error.URLError:
            pass  # All send methods exhausted — message delivery failed

    return CallToolResult(content=[TextContent(type="text",
        text=f"Send failed across all endpoints. Last error: {body[:200] if body else 'no response'}"
    )])


def _inbox_read(args: dict) -> CallToolResult:
    """Read messages. Primary: POST Bus /api/pgmq/read (dequeue).
    Fallback: GET old inbox /api/inbox."""
    log.info("inbox_read: topic=%s", args.get("topic"))

    # 🟢 Try: Bus /api/pgmq/read (dequeue — like POP)
    limit = min(args.get("limit", 10), 20)
    messages = []

    for _ in range(limit):
        status, body = _request("POST", "api/pgmq/read", {
            "queue": f"inbox_{DEFAULT_AGENT}",
            "vt": 60,  # 60s visibility timeout
        })
        if status == 200:
            try:
                msg = json.loads(body)
                if msg.get("msg_id"):
                    messages.append(msg)
                else:
                    break  # empty queue
            except json.JSONDecodeError:
                break
        else:
            break

    if messages:
        return CallToolResult(content=[TextContent(type="text",
            text=json.dumps(messages, indent=2, default=str))])

    # 🟡 Fallback: Old inbox /api/inbox
    params = {"limit": str(limit)}
    if DEFAULT_AGENT != "moses":
        params["for"] = DEFAULT_AGENT
    if t := args.get("topic"):
        params["topic"] = t
    if args.get("unread_only"):
        params["unread_only"] = "true"

    path = "api/inbox?" + urllib.parse.urlencode(params)
    status2, body2 = _request("GET", path)
    if status2 == 200:
        try:
            data = json.loads(body2)
            msgs = data.get("messages", data.get("inbox_msgs", []))[:limit]
            return CallToolResult(content=[TextContent(type="text",
                text=json.dumps(msgs, indent=2, default=str))])
        except json.JSONDecodeError:
            pass

    msg = f"No messages found."
    if status2 == 401:
        msg = "Read failed (HTTP 401). Configure CORTEX_BUS_TOKEN in ~/.hermes-cortex/cortex-bus.conf"
    return CallToolResult(content=[TextContent(type="text", text=msg)])


def _inbox_watch(args: dict) -> CallToolResult:
    """Check for new messages. Same as read, returns count."""
    limit = args.get("limit", 5)

    # Check bus queue depth first
    status, body = _request("GET", f"api/pgmq/depth/inbox_{DEFAULT_AGENT}")
    depth = 0
    if status == 200:
        try:
            depth = json.loads(body).get("depth", 0)
        except (json.JSONDecodeError, KeyError):
            pass

    if depth == 0:
        # Fallback to old inbox
        path = f"api/inbox?limit={limit}"
        if DEFAULT_AGENT != "moses":
            path += f"&for={urllib.parse.quote(DEFAULT_AGENT)}"
        status2, body2 = _request("GET", path)
        if status2 == 200:
            try:
                data = json.loads(body2)
                msgs = data.get("messages", data.get("inbox_msgs", []))
                depth = len(msgs)
            except json.JSONDecodeError:
                pass

    if depth == 0:
        return CallToolResult(content=[TextContent(type="text", text="No new messages.")])

    return CallToolResult(content=[TextContent(type="text",
        text=json.dumps({"agent": DEFAULT_AGENT, "unread": depth, "has_work": depth > 0}, indent=2))])


def _inbox_delete(args: dict) -> CallToolResult:
    """Delete/archive a message. Primary: Bus /api/pgmq/archive.
    Fallback: Old inbox /api/delete/{filename}."""
    filename = args.get("filename", "")
    if not filename:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'filename' is required.")])

    # If it's a UUID (msg_id from bus), archive via bus
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", filename, re.I):
        status, body = _request("POST", "api/pgmq/archive", {
            "queue": f"inbox_{DEFAULT_AGENT}",
            "msg_id": filename,
        })
        if status == 200:
            return CallToolResult(content=[TextContent(type="text", text=f"🗑 Archived: {filename}")])
        return CallToolResult(content=[TextContent(type="text", text=f"Archive failed (HTTP {status}): {body[:200]}")])

    # Else try old inbox delete (filename format)
    clean = filename.rstrip(".md")
    status, body = _request("DELETE", f"api/delete/{clean}")
    if status == 200:
        return CallToolResult(content=[TextContent(type="text", text=f"🗑 Deleted: {clean}")])
    return CallToolResult(content=[TextContent(type="text", text=f"Delete failed (HTTP {status}): {body[:200]})")])


# ═══════════════════════════════════════════════════════════════
# ── AGENT REGISTRY — Discovery & Agent Info ────────────────────
# ═══════════════════════════════════════════════════════════════

# Registry path (file-based, used for remote agent discovery)
# Canonical: ~/.hermes-cortex/state/agent-registry.json (setup-agent-registry.sh)
# Legacy fallback: ~/.hermes/state/agent-registry.json (pre-2026-07 installs)
STATE_REGISTRY = HOME / ".hermes-cortex" / "state" / "agent-registry.json"
LEGACY_STATE_REGISTRY = HOME / ".hermes" / "state" / "agent-registry.json"


def _load_agent_registry() -> dict:
    """Load agent registry from file. Used for remote agent discovery."""
    for path in [STATE_REGISTRY, LEGACY_STATE_REGISTRY]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load %s: %s", path, e)
    return {"agents": {}}


def _normalize_agents(registry: dict) -> list[dict]:
    """Extract and normalize agent list. Supports both list and dict formats."""
    agents = registry.get("agents", {})
    if isinstance(agents, list):
        return sorted(agents, key=lambda a: a.get("name", ""))
    result = []
    for key, entry in agents.items():
        result.append({
            "name": key,
            "display_name": entry.get("name", key.capitalize()),
            "role": entry.get("role", "unknown"),
            "url": entry.get("url", ""),
            "health_url": entry.get("health_url", ""),
            "platform": entry.get("platform", "unknown"),
            "accessible": entry.get("accessible", False),
            "agent_card_url": entry.get("agent_card_url", ""),
        })
    return sorted(result, key=lambda a: a["name"])


def _resolve_agent_url(agent_name: str) -> str | None:
    """Resolve an agent's URL from the file registry."""
    registry = _load_agent_registry()
    entry = registry.get("agents", {}).get(agent_name)
    if entry:
        return entry.get("url") or entry.get("health_url", "").replace("/health", "") or None
    return None


# ── Agent Discovery & Task Toolkit ─────────────────────────────

def _inbox_list_agents(args: dict) -> CallToolResult:
    """List agents from the file registry."""
    registry = _load_agent_registry()
    agents = _normalize_agents(registry)

    if not agents:
        return CallToolResult(content=[TextContent(type="text", text="No agents found.")])

    lines = [f"📋 {len(agents)} agent(s) found:"]
    for a in agents:
        status_icon = "🟢" if a.get("accessible") else "🔴"
        role = a.get("role", "?")
        url = a.get("url") or a.get("health_url") or "—"
        lines.append(f"  {status_icon} {a['name']:12s} ({role:22s}) {url}")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


def _inbox_get_agent(args: dict) -> CallToolResult:
    name = args.get("name", "")
    if not name:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'name' is required.")])

    registry = _load_agent_registry()
    entry = registry.get("agents", {}).get(name)
    if entry:
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(entry, indent=2))])

    return CallToolResult(content=[TextContent(type="text", text=f"Agent '{name}' not found.")])


def _inbox_discover(args: dict) -> CallToolResult:
    agent = args.get("agent", "")
    if not agent:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' is required.")])

    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Agent '{agent}' not found. Run inbox_list_agents to see available agents."
        )])

    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    try:
        req = urllib.request.Request(card_url, method="GET",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            try:
                card = json.loads(body)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(card, indent=2))])
            except json.JSONDecodeError:
                return CallToolResult(content=[TextContent(type="text",
                    text=f"Agent Card at {card_url} returned invalid JSON: {body[:200]}")])
    except urllib.error.HTTPError as e:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Could not fetch Agent Card for '{agent}' (HTTP {e.code}): {e.read().decode(errors='replace')[:200]}")])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Could not fetch Agent Card for '{agent}': {e}")])


def _inbox_send_task(args: dict) -> CallToolResult:
    """Send a task via inbox message. Uses inbox_send internally.
    No separate A2A endpoint — the task arrives as a regular inbox message."""
    agent = args.get("agent", "")
    description = args.get("description", "")
    priority = args.get("priority", "normal")
    if not agent or not description:
        return CallToolResult(content=[TextContent(type="text",
            text="Error: 'agent' and 'description' are required.")])

    import uuid
    task_id = str(uuid.uuid4())

    # Call inbox_send internally with structured task payload
    send_args = {
        "to": agent,
        "topic": "tasks",
        "subject": f"Task: {description[:80]}",
        "body": json.dumps({
            "type": "task_delegation",
            "task_id": task_id,
            "description": description,
            "priority": priority,
            "requester": DEFAULT_AGENT,
        }, indent=2),
        "priority": priority,
    }
    result = _inbox_send(send_args)
    detail = result.content[0].text if hasattr(result, 'content') and result.content else "sent"

    return CallToolResult(content=[TextContent(type="text",
        text=json.dumps({"task_id": task_id, "status": "created", "detail": detail}, indent=2))])


def _inbox_get_task(args: dict) -> CallToolResult:
    """Search inbox messages for a matching task_id."""
    agent = args.get("agent", "")
    task_id = args.get("task_id", "")
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(type="text",
            text="Error: 'agent' and 'task_id' are required.")])

    # Search inbox for messages with matching task_id
    status, body = _request("POST", "api/pgmq/read", {
        "queue": f"inbox_{DEFAULT_AGENT}",
        "vt": 1,
        "batch_size": 50,
    })
    if status != 200:
        return CallToolResult(content=[TextContent(type="text",
            text=f"Could not read inbox: HTTP {status}")])

    try:
        msgs = json.loads(body)
        if isinstance(msgs, dict):
            msgs = msgs.get("messages", msgs.get("data", []))
        if isinstance(msgs, dict):
            msgs = [msgs]
    except json.JSONDecodeError:
        msgs = []

    for msg in msgs:
        msg_body = msg.get("message", {})
        if isinstance(msg_body, str):
            try:
                msg_body = json.loads(msg_body)
            except json.JSONDecodeError:
                msg_body = {"body": msg_body}
        msg_body_str = json.dumps(msg_body)
        if task_id in msg_body_str:
            return CallToolResult(content=[TextContent(type="text",
                text=json.dumps(msg, indent=2, default=str))])

    return CallToolResult(content=[TextContent(type="text",
        text=f"Task '{task_id}' not found in current inbox.")])


def _inbox_cancel_task(args: dict) -> CallToolResult:
    """Send a cancel request via inbox message."""
    agent = args.get("agent", "")
    task_id = args.get("task_id", "")
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(type="text",
            text="Error: 'agent' and 'task_id' are required.")])

    send_args = {
        "to": agent,
        "topic": "tasks",
        "subject": f"Cancel task: {task_id[:8]}...",
        "body": json.dumps({
            "type": "task_cancel",
            "task_id": task_id,
            "requester": DEFAULT_AGENT,
        }, indent=2),
        "priority": "urgent",
    }
    result = _inbox_send(send_args)
    detail = result.content[0].text if hasattr(result, 'content') and result.content else "sent"

    return CallToolResult(content=[TextContent(type="text",
        text=json.dumps({"task_id": task_id, "status": "cancel_requested", "detail": detail}, indent=2))])


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
