#!/usr/bin/env python3
"""
orch-bus-sensor.py — Companion script for orch-process-agent-messages.

Runs every 10m as a no_agent watchdog. Calls the Agent Bus API
(via the PGMQ-based MCP backend endpoint) to check for new broadcast
messages. Silent when nothing new.

**Note:** The file-based fallback inbox is deprecated in favor of the
PGMQ Agent Bus (port 8903). This script connects to the active bus API.

Uses CORTEX_INBOX_AUTH for Basic Auth if set (user:pass format).

Output shape:
{
  "has_work": false,
  "unread_count": 0,
  "urgent_count": 0,
  "new_broadcasts": 0,
  "last_check": "2026-06-17T18:30:00Z"
}
"""
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
SEEN_FILE = STATE_DIR / "inbox-broadcast-seen"
INBOX_API = os.environ.get("CORTEX_BUS_URL", os.environ.get("CORTEX_BUS_FALLBACK_URL", ""))
INBOX_AUTH = os.environ.get("CORTEX_BUS_TOKEN", "")

# Read CORTEX_BUS_URL / CORTEX_BUS_FALLBACK_URL from config if not set via env
if not INBOX_API:
    for conf_path in [HOME / ".hermes-cortex" / "cortex-bus.conf"]:
        if conf_path.exists():
            try:
                for line in conf_path.read_text().splitlines():
                    line = line.strip()
                    val = ""
                    if line.startswith("CORTEX_BUS_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                    elif line.startswith("CORTEX_BUS_FALLBACK_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                    if val:
                        INBOX_API = val
                        break
            except Exception:
                pass
        if INBOX_API:
            break

if not INBOX_API:
    print(json.dumps({"error": "CORTEX_BUS_URL or CORTEX_BUS_FALLBACK_URL not configured — cannot connect to bus"}))
    sys.exit(1)

# Read CORTEX_BASIC_AUTH / CORTEX_BUS_AUTH / CORTEX_INBOX_AUTH from config file if not set via env
if not INBOX_AUTH:
    for conf_path in [HOME / ".hermes-cortex" / "cortex-bus.conf"]:
        if conf_path.exists():
            try:
                for line in conf_path.read_text().splitlines():
                    line = line.strip()
                    for key in ("CORTEX_BASIC_AUTH", "CORTEX_BUS_AUTH", "CORTEX_INBOX_AUTH"):
                        if line.startswith(f"{key}="):
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            if val:
                                INBOX_AUTH = val
                                break
                    if INBOX_AUTH:
                        break
            except Exception:
                pass
        if INBOX_AUTH:
            break

# Build auth header if credentials available
AUTH_HEADER = {}
if INBOX_AUTH and ":" in INBOX_AUTH:
    encoded = base64.b64encode(INBOX_AUTH.encode()).decode()
    AUTH_HEADER = {"Authorization": "Basic " + encoded}

# Read agent registry for broadcast topics
REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"


def get_broadcast_topics() -> list[str]:
    """Get broadcast topic list from agent registry."""
    default_topics = ["luke", "all", "general", "moses"]
    try:
        if REGISTRY_PATH.exists():
            data = json.loads(REGISTRY_PATH.read_text())
            topics = data.get("routing", {}).get("broadcast_topics", default_topics)
            if data.get("routing", {}).get("agent_prefix_topics", True):
                agents = data.get("agents", {})
                if isinstance(agents, dict):
                    topics.extend(agents.keys())
                elif isinstance(agents, list):
                    # agents can be ["moses", "titus"] or [{"name": "moses", ...}]
                    for a in agents:
                        if isinstance(a, str):
                            topics.append(a)
                        elif isinstance(a, dict):
                            topics.append(a.get("name", str(a)))
            return list(set(topics))
    except (json.JSONDecodeError, KeyError):
        pass
    return default_topics


def main():
    broadcast_topics = get_broadcast_topics()
    seen_ids = set()
    if SEEN_FILE.exists():
        seen_ids = set(line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip())

    # Update heartbeat file so system-alert-watchdog knows we're alive
    def _touch_check():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "last-message-check").write_text(
            datetime.now(timezone.utc).isoformat()
        )

    # Fetch messages via API with per-agent filtering
    url = f"{INBOX_API}/api/inbox?for=moses&unread_only=true"
    try:
        req = Request(url, headers=AUTH_HEADER)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, json.JSONDecodeError, OSError) as e:
        _touch_check()
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

    _touch_check()

    print(json.dumps({
        "has_work": has_work,
        "unread_count": unread_count,
        "urgent_count": urgent_count,
        "new_broadcasts": new_broadcasts,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }))


if __name__ == "__main__":
    main()