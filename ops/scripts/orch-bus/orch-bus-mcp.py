#!/usr/bin/env python3
"""
Agent Bus MCP Server — send, read, and watch messages via the Agent Bus.

Reads CORTEX_INBOX_URL, CORTEX_INBOX_AUTH, and AGENT_NAME from:
  1. Environment variables
  2. ~/.hermes-cortex/cortex-bus.conf (key=value format)

🔒  PROTECT YOUR CONFIG: chmod 600 ~/.hermes-cortex/cortex-bus.conf
     The password is sent over HTTPS (encrypted in transit).
     At-rest protection relies on filesystem permissions.

ISOLATION: Each agent can only read their own messages.
     The orchestrator (agent_name=moses) can read all.

FALLBACK: When no config is found, routes to http://localhost:8903
     (local only — messages won't reach the shared Agent Bus).
     A WARNING is logged in this case.

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

# ── Dependency Check ──────────────────────────────────────────
if importlib.util.find_spec("mcp") is None:
    print("[mcp-server] ERROR: Required 'mcp' Python package not found.", file=sys.stderr)
    print(f"[mcp-server]   {sys.executable} -m pip install mcp", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)
log = logging.getLogger("cortex-bus")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

# ── Config Loading ────────────────────────────────────────────
# Same pattern as report-agent-health.py and agent-collect-skills.sh
CONFIG_FILES = [
    Path.home() / "hermes-cortex" / ".env",
    Path.home() / ".hermes" / "cortex-bus.conf",
]

inbox_url = os.environ.get("CORTEX_INBOX_URL", "")
inbox_auth = os.environ.get("CORTEX_INBOX_AUTH", "")
agent_name = os.environ.get("AGENT_NAME", "")

for CONFIG_FILE in CONFIG_FILES:
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
                    if k == "CORTEX_INBOX_URL" and not inbox_url:
                        inbox_url = v
                    elif k == "CORTEX_INBOX_AUTH" and not inbox_auth:
                        inbox_auth = v
                    elif k == "AGENT_NAME" and not agent_name:
                        agent_name = v
        except Exception as e:
            log.warning(f"Failed to read {CONFIG_FILE}: {e}")

# Derive base URL: strip trailing path from the configured CORTEX_BUS_URL
if inbox_url:
    BASE_URL = re.sub(r"/(send|api/pgmq/.*)$", "", inbox_url)
    IS_LOCAL_FALLBACK = False
else:
    BASE_URL = "http://localhost:8903"
    IS_LOCAL_FALLBACK = True
    log.warning("❗ CORTEX_INBOX_URL not configured — routing to %s (local only). "
                "Set CORTEX_INBOX_URL in ~/.hermes-cortex/cortex-bus.conf for external agents.",
                BASE_URL)

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

# SSL context for HTTPS — client certs are deprecated
SSL_CONTEXT = ssl.create_default_context()

log.info("Inbox URL: %s  auth=%s  agent=%s",
         BASE_URL, "yes" if AUTH_HEADER else "no", DEFAULTAGENT)

PROXY_PATH = "/usr/local/bin/mcp-bus-proxy"


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


def _request(path: str, data: bytes | None = None, method: str = "POST") -> tuple[int, str]:
    """Make HTTP request to the inbox API. Returns (status_code, body).
    Tries sudo'd proxy first (for root-owned certs), falls back to direct SSL."""
    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if AUTH_HEADER:
        headers.update(AUTH_HEADER)

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

# ── Server ────────────────────────────────────────────────────
server = Server("cortex-bus")

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
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
    try:
        handlers = {"inbox_send": _inbox_send, "inbox_read": _inbox_read, "inbox_watch": _inbox_watch, "inbox_delete": _inbox_delete}
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

    status, resp_body = _request(path)
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
                 "  nano ~/.hermes-cortex/cortex-bus.conf\n"
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
    status, resp_body = _request(path)
    if status != 200:
        if status == 401:
            return CallToolResult(content=[TextContent(type="text",
                text="Watch failed (HTTP 401). Configure CORTEX_INBOX_AUTH in ~/.hermes-cortex/cortex-bus.conf")])
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
