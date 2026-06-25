#!/usr/bin/env python3
"""
Agent Inbox MCP Server — read, send, and watch the agent inbox.

Usage:
    hermes mcp add agent-inbox --command python3 --args /path/to/inbox-mcp.py

Tools:
    inbox_send      Send a message to the agent inbox
    inbox_read      Read recent messages (filtered by agent)
    inbox_watch     Poll for new messages (blocking or one-shot)
"""

import asyncio
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

INBOX_URL = "http://localhost:8903"
INBOX_DIR = Path.home() / "agent-inbox-private" / "inbox"
DEFAULTAGENT = os.environ.get("HERMES_AGENT", os.environ.get("USER", "agent"))

server = Server("agent-inbox")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="inbox_send",
            description="Send a message to the agent inbox.",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Message subject"},
                    "body": {"type": "string", "description": "Message body"},
                    "to": {"type": "string", "description": "Recipient(s) — agent name or 'all' (default)"},
                    "topic": {"type": "string", "description": "Topic channel (default: general)"},
                    "priority": {"type": "string", "enum": ["normal", "urgent", "critical"], "description": "Priority"},
                },
                "required": ["subject", "body"],
            },
        ),
        Tool(
            name="inbox_read",
            description="Read recent inbox messages. Filters by agent if 'for' is set.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages (default 10)"},
                    "for_agent": {"type": "string", "description": "Filter by recipient agent name"},
                    "topic": {"type": "string", "description": "Filter by topic channel"},
                    "unread_only": {"type": "boolean", "description": "Only unread messages"},
                },
            },
        ),
        Tool(
            name="inbox_watch",
            description="Check for new messages for this agent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name to check for (default: auto-detect)"},
                    "since_id": {"type": "string", "description": "Only show messages newer than this filename"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
    try:
        handlers = {
            "inbox_send": _inbox_send,
            "inbox_read": _inbox_read,
            "inbox_watch": _inbox_watch,
        }
        handler = handlers.get(name)
        if handler:
            return handler(args)
        return CallToolResult(content=[TextContent(type="text", text="Unknown tool: " + name)])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text="Error: " + str(e))])


def _inbox_send(args: dict) -> CallToolResult:
    body = urllib.parse.urlencode({
        "from": args.get("from", DEFAULTAGENT),
        "to": args.get("to", "moses"),
        "topic": args.get("topic", "general"),
        "subject": args["subject"],
        "body": args["body"],
        "priority": args.get("priority", "normal"),
    }).encode()
    req = urllib.request.Request(INBOX_URL + "/send", body)
    try:
        urllib.request.urlopen(req, timeout=10)
        return CallToolResult(content=[TextContent(type="text", text="Message sent.")])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text="Send failed: " + str(e))])


def _inbox_read(args: dict) -> CallToolResult:
    params = {}
    if a := args.get("for_agent"):
        params["for"] = a
    if t := args.get("topic"):
        params["topic"] = t
    if args.get("unread_only"):
        params["unread_only"] = "true"
    url = INBOX_URL + "/api/inbox"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        msgs = data.get("messages", data.get("inbox_msgs", []))[:args.get("limit", 10)]
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(msgs, indent=2, default=str))])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text="Read failed: " + str(e))])


def _inbox_watch(args: dict) -> CallToolResult:
    agent = args.get("agent", DEFAULTAGENT)
    since_id = args.get("since_id", "")
    if not INBOX_DIR.exists():
        return CallToolResult(content=[TextContent(type="text", text="No inbox directory at " + str(INBOX_DIR))])
    files = sorted(INBOX_DIR.glob("*.md"))
    if since_id:
        files = [f for f in files if f.name > since_id]
    if not files:
        return CallToolResult(content=[TextContent(type="text", text="No new messages.")])
    # Parse each file's frontmatter for to/cc fields
    new_msgs = []
    for f in files[-10:]:
        text = f.read_text(encoding="utf-8", errors="replace")[:500]
        front = {"from": "?", "subject": "?", "to": "all"}
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if m:
            for line in m.group(1).strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    front[k.strip().lower()] = v.strip()
        to_val = front.get("to", "all").lower()
        cc_val = front.get("cc", "").lower()
        if agent.lower() in to_val or agent.lower() in cc_val or "all" in to_val:
            new_msgs.append({"file": f.name, "from": front.get("from", "?"), "subject": front.get("subject", "?"), "to": to_val, "cc": cc_val})
    if not new_msgs:
        return CallToolResult(content=[TextContent(type="text", text="No new messages for " + agent + ".")])
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(new_msgs, indent=2))])


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
