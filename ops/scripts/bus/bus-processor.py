#!/usr/bin/env python3
"""orch-bus-processor.py — Companion script for bus message processing.

Runs every 10m as a no_agent watchdog. Checks the Agent Bus for
new broadcast messages via the local PGMQ endpoint.
Silent when nothing new.

Output shape:
{
  "has_work": false,
  "unread_count": 0,
  "urgent_count": 0,
  "new_broadcasts": 0,
  "last_check": "..."
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
SEEN_FILE = STATE_DIR / "bus-broadcast-seen"

# Bus connection details
BUS_URL = os.environ.get("AGENT_BUS_URL", "http://localhost:8903")
BUS_TOKEN = os.environ.get("AGENT_BUS_TOKEN", "")
AGENT = os.environ.get("AGENT_NAME", "esther")

# Token file fallback
token_file = HOME / ".hermes" / "state" / "bus.token"
if not BUS_TOKEN and token_file.exists():
    BUS_TOKEN = token_file.read_text().strip()

# Agent registry for broadcast topics
REGISTRY_PATH = HOME / ".hermes" / "state" / "agent-registry.json"


def get_broadcast_topics() -> list[str]:
    """Get broadcast topic list from agent registry."""
    default_topics = ["luke", "all", "general", "moses"]
    try:
        if REGISTRY_PATH.exists():
            data = json.loads(REGISTRY_PATH.read_text())
            topics = data.get("routing", {}).get("broadcast_topics", default_topics)
            return topics
    except (json.JSONDecodeError, KeyError):
        pass
    return default_topics


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()
    if SEEN_FILE.exists():
        seen = {line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip()}

    headers = {"Authorization": f"Bearer {BUS_TOKEN}"} if BUS_TOKEN else {}
    req = Request(f"{BUS_URL}/api/inbox?unread_only=true&for={AGENT}", headers=headers)

    try:
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
    except (URLError, json.JSONDecodeError, OSError) as e:
        result = {
            "has_work": False,
            "error": str(e)[:200],
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(result))
        return 0

    messages = data.get("messages", []) if isinstance(data, dict) else []
    unread_count = data.get("unread", len(messages)) if isinstance(data, dict) else len(messages)

    broadcast_topics = set(get_broadcast_topics())
    new_broadcasts = [m for m in messages if m.get("topic", "").lower() in broadcast_topics]

    result = {
        "has_work": len(new_broadcasts) > 0,
        "unread_count": unread_count,
        "urgent_count": sum(1 for m in messages if m.get("priority") == "urgent" or m.get("priority") == "critical"),
        "new_broadcasts": len(new_broadcasts),
        "last_check": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    main()
