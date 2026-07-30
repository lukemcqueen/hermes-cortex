#!/usr/bin/env python3
"""agent-bus-processor.py — Companion script for bus message processing.

Runs every 10m as a no_agent watchdog. Checks the Agent Bus for
new broadcast messages via the bus library (lib.cortex_bus).
Silent when nothing new.

Uses bus_list_queues() to peek at queue depths (non-consuming),
then bus_read() to inspect individual messages.

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
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the hermes-cortex scripts dir is in sys.path for lib.cortex_bus
_HC_SCRIPTS = Path.home() / ".hermes-cortex" / "scripts"
if str(_HC_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_HC_SCRIPTS))

from lib.cortex_bus import bus_list_queues, bus_read, bus_archive

HOME = Path.home()
STATE_DIR = HOME / ".hermes" / "state"
SEEN_FILE = STATE_DIR / "bus-broadcast-seen"
AGENT = os.environ.get("AGENT_NAME", "esther")

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
        pass  # expected — silently handled
    return default_topics


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()
    if SEEN_FILE.exists():
        seen = {line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip()}

    # Check all queues for our agent's inbox depth
    inbox_queue = f"inbox_{AGENT}"
    broadcast_topics = set(get_broadcast_topics())

    try:
        queues = bus_list_queues()
        inbox_info = next((q for q in queues if q.get("name") == inbox_queue), None)
        if inbox_info is None:
            print(json.dumps({
                "has_work": False,
                "unread_count": 0,
                "urgent_count": 0,
                "new_broadcasts": 0,
                "error": f"Queue '{inbox_queue}' not found",
                "last_check": datetime.now(timezone.utc).isoformat(),
            }))
            return 0

        depth = inbox_info.get("depth", 0)
        if depth == 0:
            print(json.dumps({
                "has_work": False,
                "unread_count": 0,
                "urgent_count": 0,
                "new_broadcasts": 0,
                "last_check": datetime.now(timezone.utc).isoformat(),
            }))
            return 0

    except Exception as e:
        print(json.dumps({
            "has_work": False,
            "unread_count": 0,
            "urgent_count": 0,
            "new_broadcasts": 0,
            "error": str(e)[:200],
            "last_check": datetime.now(timezone.utc).isoformat(),
        }))
        return 0

    # Peek at messages — read, inspect, archive (non-destructive)
    unread_count = 0
    urgent_count = 0
    new_broadcasts = 0
    messages_read = []

    for _ in range(min(depth, 20)):
        msg = bus_read(inbox_queue, vt=30)
        if not msg or not msg.get("msg_id"):
            break

        body = msg.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                pass  # expected — silently handled

        topic = (body or {}).get("topic", "general") if isinstance(body, dict) else "general"
        priority = (body or {}).get("priority", "normal") if isinstance(body, dict) else "normal"
        msg_id = msg.get("msg_id", "")
        corr = msg.get("correlation_id", "")

        if topic in broadcast_topics:
            unread_count += 1
            if priority in ("urgent", "critical"):
                urgent_count += 1
            if corr not in seen and msg_id not in seen:
                new_broadcasts += 1

        messages_read.append(msg_id)
        bus_archive(inbox_queue, msg_id)

    # Record seen IDs
    for mid in messages_read:
        seen.add(mid)
    SEEN_FILE.write_text("\n".join(sorted(seen)))

    has_work = new_broadcasts > 0 or urgent_count > 0

    print(json.dumps({
        "has_work": has_work,
        "unread_count": unread_count,
        "urgent_count": urgent_count,
        "new_broadcasts": new_broadcasts,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
