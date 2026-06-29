#!/usr/bin/env python3
"""agent-inbox-processor.py — Companion script for process-agent-messages.

Runs every 10m as a no_agent watchdog. Calls the agent inbox API to check
for new broadcast messages. Silent when nothing new.

This eliminates the duplicate frontmatter parser and uses the API's
per-agent read tracking via the ?for=moses parameter.

Output shape:
{
  "has_work": false,
  "unread_count": 0,
  "urgent_count": 0,
  "new_broadcasts": 0,
  "last_check": "2026-06-17T18:30:00Z"
}
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path.home()
STATE_DIR = HOME / ".hermes" / "state"
SEEN_FILE = STATE_DIR / "inbox-broadcast-seen"

# Source config from agent-inbox.conf if available, fall back to env var
INBOX_API = os.environ.get("AGENT_INBOX_URL", "")
INBOX_USER = os.environ.get("AGENT_INBOX_USER", "")
INBOX_PASS = os.environ.get("AGENT_INBOX_PASS", "")
conf_path = HOME / ".hermes" / "agent-inbox.conf"
if conf_path.exists():
    for line in conf_path.read_text().splitlines():
        line = line.strip()
        if "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip("'\"")
            if k == "AGENT_INBOX_URL" and not INBOX_API:
                INBOX_API = v
            elif k == "AGENT_INBOX_USER" and not INBOX_USER:
                INBOX_USER = v
            elif k == "AGENT_INBOX_PASS" and not INBOX_PASS:
                INBOX_PASS = v
if not INBOX_API:
    INBOX_API = "https://your-domain.com:13004"

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


def main():
    broadcast_topics = get_broadcast_topics()
    seen_ids = set()
    if SEEN_FILE.exists():
        seen_ids = set(line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip())

    # Fetch messages via API with per-agent filtering
    url = f"{INBOX_API}/api/inbox?for=moses&unread_only=true"
    try:
        req = Request(url)
        if INBOX_USER and INBOX_PASS:
            import base64
            auth = base64.b64encode(f"{INBOX_USER}:{INBOX_PASS}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(json.dumps({
            "has_work": False,
            "unread_count": 0,
            "urgent_count": 0,
            "new_broadcasts": 0,
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat(),
        }))
        return

    messages = data.get("messages", [])
    unread_count = 0
    urgent_count = 0
    new_broadcasts = 0

    for m in messages:
        topic = m.get("topic", "general")
        priority = m.get("priority", "normal")
        msg_id = m.get("id", "")

        if topic in broadcast_topics:
            unread_count += 1
            if priority in ("urgent", "critical"):
                urgent_count += 1
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