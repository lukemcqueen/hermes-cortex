#!/usr/bin/env python3
"""
Inbox Watcher — checks for new messages from other agents via file-based fallback inbox.

**⚠️ LEGACY: The file-based inbox is deprecated in favor of the PGMQ Agent Bus (port 8903).**
This script only works on machines with the private repo mounted
(`~/hermes-cortex-private/messages/inbox/`). Use MCP tools (`inbox_send` / `inbox_read` / `inbox_watch`)
for Agent Bus access.

Runs at session start (I call it manually) and can run as a cron.
Flags messages that need my attention: skill-miner findings, requests,
questions, and anything tagged 'urgent' or 'critical'.

Usage:
    python3 inbox-watcher.py              # check and report
    python3 inbox-watcher.py --mark-read  # check + mark as processed

Uses AGENT_INBOX_URL env var with fallback to external URL.
Reads CORTEX_INBOX_AUTH from env or ~/.hermes-cortex/hermes-inbox.conf for Basic Auth.
"""
import base64
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Inbox URL ──
INBOX_URL = os.environ.get(
    "AGENT_INBOX_URL",
    "https://your-domain.com:13004",
)

# ── Auth ──
INBOX_AUTH = os.environ.get("CORTEX_INBOX_AUTH", "")
if not INBOX_AUTH:
    config_path = Path.home() / ".hermes-cortex" / "hermes-inbox.conf"
    if config_path.exists():
        try:
            for line in config_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("CORTEX_INBOX_AUTH="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val:
                        INBOX_AUTH = val
                        break
        except Exception:
            pass

AUTH_HEADER = {}
if INBOX_AUTH and ":" in INBOX_AUTH:
    encoded = base64.b64encode(INBOX_AUTH.encode()).decode()
    AUTH_HEADER = {"Authorization": f"Basic {encoded}"}

INBOX_DIR = Path.home() / "agent-inbox-private" / "inbox"
LAST_SEEN_FILE = Path.home() / ".hermes-cortex" / "data" / "inbox-last-seen.txt"


def fetch_inbox_html() -> str:
    """Fetch inbox page and extract message threads."""
    try:
        req = urllib.request.Request(f"{INBOX_URL}/?topic=moses", headers=AUTH_HEADER)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"<!-- ERROR: {e} -->"


def check_inbox_files() -> list[dict]:
    """Scan inbox files for new messages from agents."""
    messages = []
    if not INBOX_DIR.exists():
        return messages

    last_seen = ""
    if LAST_SEEN_FILE.exists():
        last_seen = LAST_SEEN_FILE.read_text().strip()

    for f in sorted(INBOX_DIR.glob("*.md")):
        if last_seen and f.name <= last_seen:
            continue  # already processed

        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            messages.append({
                "file": f.name,
                "from": _extract_field(text, "from"),
                "topic": _extract_field(text, "topic"),
                "subject": _extract_field(text, "subject"),
                "priority": _extract_field(text, "priority", "normal"),
                "body": _extract_body(text),
            })
        except Exception:
            continue

    return messages


def _extract_field(text: str, field: str, default: str = "unknown") -> str:
    for line in text.split("\n")[:15]:
        if line.lower().startswith(f"{field}:"):
            return line.split(":", 1)[1].strip()
    return default


def _extract_body(text: str) -> str:
    lines = text.split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("body:"):
            body_start = i + 1
            break
    return "\n".join(lines[body_start:]).strip()[:2000]


def main():
    print(f"\n═ Inbox Watch — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ═\n")

    # Scan inbox files
    messages = check_inbox_files()

    if not messages:
        print("  No new messages from agents.")
        print()
        return

    print(f"  {len(messages)} new message(s):")
    print()

    urgent = [m for m in messages if m.get("priority") in ("urgent", "critical")]
    normal = [m for m in messages if m.get("priority") not in ("urgent", "critical")]

    for m in urgent:
        icon = "🔴" if m["priority"] == "critical" else "⚠️"
        print(f"  {icon} [{m['from']:<10}] {m['subject']}")
        print(f"     Priority: {m['priority']}")
        print(f"     Topic: {m['topic']}")
        print(f"     Body: {m['body'][:200]}")
        print()

    for m in normal:
        print(f"  📩 [{m['from']:<10}] {m['subject']}")
        print(f"     Topic: {m['topic']}")
        print(f"     Body: {m['body'][:200]}")
        print()

    # Mark as seen
    if messages:
        newest = max(m["file"] for m in messages)
        os.makedirs(LAST_SEEN_FILE.parent, exist_ok=True)
        with open(LAST_SEEN_FILE, "w") as f:
            f.write(newest)
        print(f"  Marked as seen (up to {newest})")

    # Summary for session start
    print(f"  ⚡ {len(urgent)} urgent, {len(normal)} normal — review above before proceeding")
    print()


if __name__ == "__main__":
    main()
