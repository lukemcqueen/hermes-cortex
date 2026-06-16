#!/usr/bin/env python3
"""inbox-sensor.py — Companion script for process-agent-messages.

Runs every 10m as a no_agent watchdog. Checks the agent inbox for new
broadcast messages and outputs structured JSON if there's work to do.
Silent when nothing new (empty JSON array = nothing to process).

This allows the LLM-tier process-agent-messages cron to skip processing
when there's nothing to do, saving ~120 LLM calls/day.

Output: JSON object with workload summary on stdout.

Output shape:
{
  "has_work": false,           # true if there are new broadcasts to process
  "unread_count": 0,           # total unread messages in inbox
  "urgent_count": 0,           # messages with urgent/critical priority
  "new_broadcasts": 0,         # broadcasts not yet seen by Moses
  "last_check": "2026-06-15T18:30:00Z"
}

Called from process-agent-messages prompt via prompt context injection
(scheduled as a no_agent cron running every 10m with deliver=local).
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PRIVATE_REPO = HOME / "hermes-cortex-private"
INBOX_DIR = PRIVATE_REPO / "messages" / "inbox"
STATE_DIR = HOME / ".hermes" / "state"
SEEN_FILE = STATE_DIR / "inbox-broadcast-seen"

# Read agent registry for broadcast topics
REGISTRY_PATH = HOME / ".hermes" / "state" / "agent-registry.json"


def get_broadcast_topics() -> list[str]:
    """Get broadcast topic list from agent registry."""
    default_topics = ["luke", "all", "general", "moses"]
    try:
        if REGISTRY_PATH.exists():
            data = json.loads(REGISTRY_PATH.read_text())
            topics = data.get("routing", {}).get("broadcast_topics", default_topics)
            if data.get("routing", {}).get("agent_prefix_topics", True):
                topics.extend(data.get("agents", {}).keys())
            return list(set(topics))
    except (json.JSONDecodeError, KeyError):
        pass
    return default_topics


def parse_frontmatter(path: Path) -> dict:
    """Extract frontmatter fields from a message file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    front = {"from": "?", "subject": "No subject", "topic": "general", "priority": "normal"}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m:
        for line in m.group(1).strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                front[k.strip().lower()] = v.strip()
    return front


def main():
    # Check if inbox directory exists
    if not INBOX_DIR.exists():
        print(json.dumps({
            "has_work": False,
            "unread_count": 0,
            "urgent_count": 0,
            "new_broadcasts": 0,
            "error": f"Inbox directory not found: {INBOX_DIR}",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }))
        return

    broadcast_topics = get_broadcast_topics()
    seen_ids = set()
    if SEEN_FILE.exists():
        seen_ids = set(line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip())

    inbox_files = sorted(INBOX_DIR.glob("*.md"))
    unread_count = 0
    urgent_count = 0
    new_broadcasts = 0

    for msg_file in inbox_files:
        front = parse_frontmatter(msg_file)
        topic = front.get("topic", "general")
        priority = front.get("priority", "normal")
        status = front.get("status", "unread")
        msg_id = msg_file.stem

        # Skip already-read messages
        if status == "read":
            continue

        # Only count broadcast messages (stays in inbox for agents)
        if topic in broadcast_topics:
            unread_count += 1
            if priority in ("urgent", "critical"):
                urgent_count += 1
            # New broadcast not yet seen by Moses
            if msg_id not in seen_ids:
                new_broadcasts += 1

    has_work = new_broadcasts > 0 or urgent_count > 0

    print(json.dumps({
        "has_work": has_work,
        "unread_count": unread_count,
        "urgent_count": urgent_count,
        "new_broadcasts": new_broadcasts,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }))


if __name__ == "__main__":
    main()