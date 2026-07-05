#!/usr/bin/env python3
"""
Agent Inbox MCP Server — send, read, and watch the agent inbox.

Reads CORTEX_INBOX_URL, CORTEX_INBOX_FALLBACK_URL, CORTEX_INBOX_THIRD_URL,
CORTEX_INBOX_AUTH, and AGENT_NAME from:
  1. Environment variables
  2. ~/.hermes/hermes-inbox.conf (key=value format)

🔒  PROTECT YOUR CONFIG: chmod 600 ~/.hermes/hermes-inbox.conf
     The password is sent over HTTPS (encrypted in transit).
     At-rest protection relies on filesystem permissions.

ISOLATION: Each agent can only read their own messages.
     The orchestrator (agent_name=moses) can read all.

FALLBACK CHAIN: When a URL fails (connection error), the next URL in the chain
     is tried. Up to 3 levels: primary → fallback → third → localhost:8903.

Tools:
    inbox_send      Send message + optional file attachment (5 MB max)
    inbox_read      Read recent messages (always filtered to your agent)
    inbox_watch     Check for new messages for your agent
    inbox_delete    Delete a message (moves to trash/)
"""

import asyncio
import base64
import importlib.util
import json
import logging
import os
import re
import ssl
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

logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)
log = logging.getLogger("agent-inbox")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

# ── Config Loading ────────────────────────────────────────────
# Primary: hermes-inbox.conf. Fallback: moses-inbox.conf (deprecated).
CONFIG_FILE = Path.home() / ".hermes" / "hermes-inbox.conf"
CONFIG_FILE_OLD = Path.home() / ".hermes" / "moses-inbox.conf"
if not CONFIG_FILE.exists() and CONFIG_FILE_OLD.exists():
    log.warning("⚠️  ~/.hermes/moses-inbox.conf is deprecated — rename to hermes-inbox.conf")
    CONFIG_FILE = CONFIG_FILE_OLD

# Check CORTEX_INBOX_* env vars first, fall back to MOSES_INBOX_* (deprecated)
inbox_url = os.environ.get("CORTEX_INBOX_URL", "")
if not inbox_url:
    old_val = os.environ.get("MOSES_INBOX_URL", "")
    if old_val:
        log.warning("⚠️  MOSES_INBOX_URL is deprecated — use CORTEX_INBOX_URL")
        inbox_url = old_val

inbox_fallback_url = os.environ.get("CORTEX_INBOX_FALLBACK_URL", "")
if not inbox_fallback_url:
    old_val = os.environ.get("MOSES_INBOX_FALLBACK_URL", "")
    if old_val:
        log.warning("⚠️  MOSES_INBOX_FALLBACK_URL is deprecated — use CORTEX_INBOX_FALLBACK_URL")
        inbox_fallback_url = old_val

inbox_third_url = os.environ.get("CORTEX_INBOX_THIRD_URL", "")
if not inbox_third_url:
    old_val = os.environ.get("MOSES_INBOX_THIRD_URL", "")
    if old_val:
        log.warning("⚠️  MOSES_INBOX_THIRD_URL is deprecated — use CORTEX_INBOX_THIRD_URL")
        inbox_third_url = old_val

inbox_auth = os.environ.get("CORTEX_INBOX_AUTH", "")
if not inbox_auth:
    old_val = os.environ.get("MOSES_INBOX_AUTH", "")
    if old_val:
        log.warning("⚠️  MOSES_INBOX_AUTH is deprecated — use CORTEX_INBOX_AUTH")
        inbox_auth = old_val

agent_name = os.environ.get("AGENT_NAME", "")

# Config file keys: accept both CORTEX_ and MOSES_ prefixes
_OLD_KEYS = {
    "MOSES_INBOX_URL": "CORTEX_INBOX_URL",
    "MOSES_INBOX_FALLBACK_URL": "CORTEX_INBOX_FALLBACK_URL",
    "MOSES_INBOX_THIRD_URL": "CORTEX_INBOX_THIRD_URL",
    "MOSES_INBOX_AUTH": "CORTEX_INBOX_AUTH",
}

if CONFIG_FILE.exists():
    try:
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                # Strip inline comments (everything after # preceded by whitespace)
                import re as _re
                v = _re.sub(r"\s+#.*$", "", v).strip()
                # Map old key names to new ones
                mapped_k = _OLD_KEYS.get(k, k)
                if mapped_k == "CORTEX_INBOX_URL" and not inbox_url:
                    inbox_url = v
                elif mapped_k == "CORTEX_INBOX_FALLBACK_URL" and not inbox_fallback_url:
                    inbox_fallback_url = v
                elif mapped_k == "CORTEX_INBOX_THIRD_URL" and not inbox_third_url:
                    inbox_third_url = v
                elif mapped_k == "CORTEX_INBOX_AUTH" and not inbox_auth:
                    inbox_auth = v
                elif k == "AGENT_NAME" and not agent_name:
                    agent_name = v
    except Exception as e:
        log.warning("Failed to read %s: %s", CONFIG_FILE, e)

# Build the URL chain: primary → fallback → third → localhost fallback
_URL_LIST = []
if inbox_url:
    _URL_LIST.append(("Moses (primary)", re.sub(r"/(send|api/inbox).*$", "", inbox_url)))
if inbox_fallback_url:
    _URL_LIST.append(("Esther (fallback)", re.sub(r"/(send|api/inbox).*$", "", inbox_fallback_url)))
if inbox_third_url:
    _URL_LIST.append(("Local (3rd)", re.sub(r"/(send|api/inbox).*$", "", inbox_third_url)))
# Always append the base localhost fallback as last resort
_URL_LIST.append(("localhost (last resort)", "http://127.0.0.1:8903"))

IS_LOCAL_FALLBACK = not bool(inbox_url)
if IS_LOCAL_FALLBACK:
    log.warning("❗ CORTEX_INBOX_URL not configured — using localhost only. "
                "Set CORTEX_INBOX_URL in ~/.hermes/hermes-inbox.conf for external agents.")

log.info("Inbox routing chain:")
for name, url in _URL_LIST:
    log.info("  %s: %s", name, url)

# Build auth header if credentials available
AUTH_HEADER = None
if inbox_auth:
    encoded = base64.b64encode(inbox_auth.encode()).decode()
    AUTH_HEADER = {"Authorization": "Basic " + encoded}

# Resolve agent identity: AGENT_NAME > auth username > USER env
if not agent_name and inbox_auth and ":" in inbox_auth:
    agent_name = inbox_auth.split(":", 1)[0]
if not agent_name:
    agent_name = os.environ.get("USER", "")
if not agent_name:
    log.warning("AGENT_NAME not configured — using 'agent' as fallback")
    agent_name = "agent"

DEFAULTAGENT = agent_name

# Build SSL context with MCP client cert (required by nginx for external endpoint)
CERT_DIR = Path.home() / ".hermes-cortex" / "certs"
CLIENT_CERT = CERT_DIR / "hermes-mcp-client.crt"
CLIENT_KEY = CERT_DIR / "hermes-mcp-client.key"
SSL_CONTEXT = None
if CERT_DIR.exists() and CLIENT_CERT.exists() and CLIENT_KEY.exists():
    try:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.load_cert_chain(str(CLIENT_CERT), str(CLIENT_KEY))
        SSL_CONTEXT = ctx
        log.info("Loaded MCP client cert from %s", CLIENT_CERT)
    except Exception as e:
        log.warning("Failed to load client cert: %s", e)
        SSL_CONTEXT = None
else:
    ctx = None
    if IS_LOCAL_FALLBACK:
        log.info("No client cert — using localhost fallback (no cert required)")
    else:
        log.warning("MCP client cert not found at %s — external requests will fail",
                    CLIENT_CERT)

log.info("Inbox agent=%s  auth=%s  cert=%s",
         DEFAULTAGENT, "yes" if AUTH_HEADER else "no",
         "loaded" if SSL_CONTEXT else "none")

PROXY_PATH = "/usr/local/bin/mcp-inbox-proxy"


def _call_proxy(url: str, method: str, data: bytes | None, headers: dict) -> tuple[int, str]:
    """Make HTTPS request via the sudo'd proxy binary.
    The proxy reads root-owned certs that the agent user can't access."""
    import subprocess
    payload = json.dumps({
        "url": url,
        "method": method,
        "data": data.decode() if data else None,
        "headers": headers,
    })
    try:
        r = subprocess.run(
            ["sudo", "-n", PROXY_PATH],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if r.returncode == 0 and r.stdout.strip():
            result = json.loads(r.stdout)
            return result.get("status", 0), result.get("body", "")
        return 0, r.stderr or f"Proxy exited {r.returncode}"
    except FileNotFoundError:
        return 0, "mcp-inbox-proxy not found"
    except Exception as e:
        return 0, str(e)


def _do_request(url: str, data: bytes | None, method: str, headers: dict) -> tuple[int, str]:
    """Try a single HTTP request to the given URL. Returns (status, body)."""
    # Try proxy first
    if Path(PROXY_PATH).exists():
        status, body = _call_proxy(url, method, data, headers)
        if status != 0:
            return status, body

    # Fall back to direct SSL
    try:
        req = urllib.request.Request(url, data=data or None, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, body
    except Exception as e:
        return 0, str(e)


def _request(path: str, data: bytes | None = None, method: str = "POST") -> tuple[int, str]:
    """Make HTTP request to the inbox API, trying each URL in the chain.
    Returns (status_code, body) from the first URL that returns a valid HTTP response.
    Connection errors (status=0) cascade to the next URL in the chain."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if AUTH_HEADER:
        headers.update(AUTH_HEADER)

    last_error = ""
    for name, base_url in _URL_LIST:
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        log.info("Trying %s: %s", name, url)
        status, resp_body = _do_request(url, data, method, headers)
        if status != 0:
            # Got a real HTTP response — server is alive
            # BUT: 401 means auth mismatch, not a usable endpoint — cascade
            # Also cascade on 403 (forbidden) and 404 (wrong path)
            if status in (401, 403, 404):
                log.warning("  %s responded HTTP %s (cascading), trying next in chain", name, status)
                last_error = f"HTTP {status}"
                continue
            log.info("  %s responded HTTP %s", name, status)
            return status, resp_body
        # Connection error — log and cascade to next URL
        last_error = resp_body
        log.warning("  %s unreachable (%s), trying next in chain", name, resp_body)

    # All URLs failed
    return 0, f"All inbox endpoints unreachable. Last error: {last_error}"


# ── Server ────────────────────────────────────────────────────
server = Server("agent-inbox")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="inbox_send",
            description="Send a message to the agent inbox, optionally with a file attachment (max 5 MB).",
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
            description="Read recent inbox messages. Always filtered to your agent (set via AGENT_NAME in config).",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages (default 10)"},
                    "topic": {"type": "string", "description": "Filter by topic channel"},
                    "unread_only": {"type": "boolean", "description": "Only unread messages"},
                },
            },
        ),
        Tool(
            name="inbox_watch",
            description="Check for new messages for your agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent messages to check (default 5)"},
                },
            },
        ),
        Tool(
            name="inbox_delete",
            description="Delete a message from the inbox. Moves to trash/ (recoverable).",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Message filename (e.g. '20260625090000-titus.md')"},
                },
                "required": ["filename"],
            },
        ),
        # ── A2A Bridge Tools ──
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
            description="Submit a task to a remote agent via A2A protocol. Returns task ID for status polling.",
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
            description="Poll the status of an A2A task on a remote agent.",
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
            description="Cancel a pending A2A task on a remote agent.",
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

# ── Tool Implementations ──────────────────────────────────────
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

def _inbox_send(args: dict) -> CallToolResult:
    log.info("inbox_send: to=%s topic=%s", args.get("to"), args.get("topic"))
    body_text = args["body"]

    # Handle optional file attachment
    fp_arg = args.get("file_path", "")
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

    data = urllib.parse.urlencode({
        "from": args.get("from", DEFAULTAGENT),
        "to": args.get("to", "moses"),
        "topic": args.get("topic", "general"),
        "subject": args["subject"],
        "body": body_text,
        "priority": args.get("priority", "normal"),
    }).encode()

    status, resp_body = _request("send", data)
    if status == 200:
        fp = args.get("file_path", "")
        tag = f" + {Path(fp.strip()).expanduser().name}" if fp and fp.strip() else ""
        return CallToolResult(content=[TextContent(type="text", text=f"Message sent{tag}.")])
    else:
        return CallToolResult(content=[TextContent(type="text", text=f"Send failed (HTTP {status}): {resp_body}")])

def _inbox_read(args: dict) -> CallToolResult:
    log.info("inbox_read: topic=%s", args.get("topic"))
    params = {}
    # Orchestrator (moses) reads all; other agents read only their own inbox
    if DEFAULTAGENT != "moses":
        params["for"] = DEFAULTAGENT
    if t := args.get("topic"):
        params["topic"] = t
    if args.get("unread_only"):
        params["unread_only"] = "true"

    path = "api/inbox"
    if params:
        path += "?" + urllib.parse.urlencode(params)

    status, resp_body = _request(path, method="GET")
    if status == 200:
        try:
            data = json.loads(resp_body)
            msgs = data.get("messages", data.get("inbox_msgs", []))[:args.get("limit", 10)]
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(msgs, indent=2, default=str))])
        except json.JSONDecodeError:
            return CallToolResult(content=[TextContent(type="text", text=f"Read returned invalid JSON (HTTP {status})")])
    elif status == 401:
        return CallToolResult(content=[TextContent(type="text",
            text="Read failed (HTTP 401 Unauthorized). Configure credentials:\n"
                 "  nano ~/.hermes/hermes-inbox.conf\n"
                 "  Set: CORTEX_INBOX_AUTH=user:pass")])
    else:
        return CallToolResult(content=[TextContent(type="text", text=f"Read failed (HTTP {status}): {resp_body}")])

def _inbox_watch(args: dict) -> CallToolResult:
    limit = args.get("limit", 5)
    log.info("inbox_watch: agent=%s limit=%s", DEFAULTAGENT, limit)

    # Orchestrator (moses) reads all; other agents read only their own inbox
    path = f"api/inbox?limit={limit}"
    if DEFAULTAGENT != "moses":
        path += f"&for={urllib.parse.quote(DEFAULTAGENT)}"
    status, resp_body = _request(path, method="GET")
    if status != 200:
        if status == 401:
            return CallToolResult(content=[TextContent(type="text",
                text="Watch failed (HTTP 401). Configure CORTEX_INBOX_AUTH in ~/.hermes/hermes-inbox.conf")])
        return CallToolResult(content=[TextContent(type="text", text=f"Watch failed (HTTP {status}): {resp_body}")])

    try:
        data = json.loads(resp_body)
        msgs = data.get("messages", data.get("inbox_msgs", []))
        if not msgs:
            return CallToolResult(content=[TextContent(type="text", text="No new messages.")])
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(msgs, indent=2, default=str))])
    except json.JSONDecodeError:
        return CallToolResult(content=[TextContent(type="text", text="Watch returned invalid JSON.")])


def _inbox_delete(args: dict) -> CallToolResult:
    filename = args.get("filename", "")
    if not filename:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'filename' is required.")])

    # Strip .md if provided
    clean = filename.rstrip(".md")

    status, resp_body = _request(f"api/delete/{clean}", method="DELETE")
    if status == 200:
        return CallToolResult(content=[TextContent(type="text", text=f"🗑 Deleted: {clean}")])
    else:
        return CallToolResult(content=[TextContent(type="text", text=f"Delete failed (HTTP {status}): {resp_body}")])


# ── A2A Bridge — Agent Discovery & Task Delegation ─────────────

# Registry paths
A2A_REGISTRY = HOME / ".hermes-cortex" / "a2a" / "agent-registry.json"
STATE_REGISTRY = HOME / ".hermes" / "state" / "agent-registry.json"

# mTLS client cert (for A2A cross-server requests)
CERT_DIR = HOME / ".hermes-cortex" / "certs"
CLIENT_CERT = CERT_DIR / "hermes-mcp-client.crt"
CLIENT_KEY = CERT_DIR / "hermes-mcp-client.key"

_A2A_SSL_CONTEXT = None
if CLIENT_CERT.exists() and CLIENT_KEY.exists():
    try:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.load_cert_chain(str(CLIENT_CERT), str(CLIENT_KEY))
        _A2A_SSL_CONTEXT = ctx
        log.info("Loaded A2A mTLS client cert from %s", CLIENT_CERT)
    except Exception as e:
        log.warning("Failed to load A2A mTLS client cert: %s", e)


def _load_agent_registry() -> dict:
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
    """Resolve an agent's base URL from the registry."""
    registry = _load_agent_registry()
    entry = registry.get("agents", {}).get(agent_name)
    if not entry:
        return None
    return entry.get("url") or entry.get("health_url", "").replace("/health", "") or None


def _a2a_http_get(url: str, timeout: int = 10) -> tuple[int, str]:
    """Make an HTTPS GET request with basic auth + optional mTLS client cert."""
    try:
        headers = {"Accept": "application/json"}
        if AUTH_HEADER:
            headers.update(AUTH_HEADER)
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=_A2A_SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, body
    except Exception as e:
        return 0, str(e)


def _a2a_http_post(url: str, data: bytes, timeout: int = 15) -> tuple[int, str]:
    """Make an HTTPS POST request with basic auth + JSON body + optional mTLS client cert."""
    try:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if AUTH_HEADER:
            headers.update(AUTH_HEADER)
        req = urllib.request.Request(
            url, data=data, method="POST", headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_A2A_SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, body
    except Exception as e:
        return 0, str(e)


# ── A2A Tool Implementations ──

def _inbox_list_agents(args: dict) -> CallToolResult:
    registry = _load_agent_registry()
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


def _inbox_get_agent(args: dict) -> CallToolResult:
    name = args.get("name", "")
    if not name:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'name' is required.")])
    registry = _load_agent_registry()
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


def _inbox_discover(args: dict) -> CallToolResult:
    agent = args.get("agent", "")
    if not agent:
        return CallToolResult(content=[TextContent(type="text", text="Error: 'agent' is required.")])
    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Agent '{agent}' not found in registry. Run inbox_list_agents to see available agents."
        )])
    card_urls = [
        f"{base_url.rstrip('/')}/.well-known/agent-card.json",
        f"{base_url.rstrip('/')}/a2a/agent-card",
    ]
    for card_url in card_urls:
        status, body = _a2a_http_get(card_url)
        if status == 200:
            try:
                card = json.loads(body)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(card, indent=2))])
            except json.JSONDecodeError:
                return CallToolResult(content=[TextContent(
                    type="text", text=f"Agent Card at {card_url} returned invalid JSON: {body[:200]}"
                )])
    return CallToolResult(content=[TextContent(
        type="text", text=f"Could not fetch Agent Card for '{agent}' — tried {', '.join(card_urls)}."
    )])


def _inbox_send_task(args: dict) -> CallToolResult:
    agent = args.get("agent", "")
    description = args.get("description", "")
    priority = args.get("priority", "normal")
    if not agent or not description:
        return CallToolResult(content=[TextContent(
            type="text", text="Error: 'agent' and 'description' are required."
        )])
    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Agent '{agent}' not found in registry."
        )])
    url = f"{base_url.rstrip('/')}/a2a/task"
    payload = json.dumps({
        "jsonrpc": "2.0", "id": f"hermes-{HOME.name}",
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
    status_code, body = _a2a_http_post(url, payload)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Task submission failed (HTTP {status_code}): {body[:300] if body else 'no response'}"
        )])


def _inbox_get_task(args: dict) -> CallToolResult:
    agent = args.get("agent", "")
    task_id = args.get("task_id", "")
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(
            type="text", text="Error: 'agent' and 'task_id' are required."
        )])
    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Agent '{agent}' not found in registry."
        )])
    url = f"{base_url.rstrip('/')}/a2a/task/{task_id}"
    status_code, body = _a2a_http_get(url)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Task query failed (HTTP {status_code}): {body[:300] if body else 'no response'}"
        )])


def _inbox_cancel_task(args: dict) -> CallToolResult:
    agent = args.get("agent", "")
    task_id = args.get("task_id", "")
    if not agent or not task_id:
        return CallToolResult(content=[TextContent(
            type="text", text="Error: 'agent' and 'task_id' are required."
        )])
    base_url = _resolve_agent_url(agent)
    if not base_url:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Agent '{agent}' not found in registry."
        )])
    url = f"{base_url.rstrip('/')}/a2a/task/{task_id}/cancel"
    payload = json.dumps({"jsonrpc": "2.0", "id": 1}).encode()
    status_code, body = _a2a_http_post(url, payload)
    if status_code == 200:
        return CallToolResult(content=[TextContent(type="text", text=body)])
    else:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Task cancellation failed (HTTP {status_code}): {body[:300] if body else 'no response'}"
        )])


# ── Main ──────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
