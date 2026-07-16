#!/usr/bin/env python3
"""bus-forwarder.py — Sync messages from Moses' bus to Esther's local bus.

no_agent watchdog pattern:
  Empty stdout → silent (no new messages to forward)
  Text output  → delivered (messages forwarded)

Runs every 2 minutes. Polls Moses' bus for messages in agent queues,
forwards unseen msg_ids to Esther's local bus (shared Postgres).
Tracks seen msg_ids in ~/.hermes-cortex/state/bus-forwarder-state.json
so each message is forwarded exactly once.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "bus-forwarder-state.json"
TIMEOUT = 15

# Moses' external bus (primary)
MOSES_URL = "https://bus.example.org:13004"
MOSES_AUTH = "esther:d01931493c7a4f7d"

# My local bus (backup)
LOCAL_URL = "http://127.0.0.1:8905"
LOCAL_TOKEN = "hbus_d2739edfda4885356707e97cb8e39e730c721c26f258ce91e190b2254d80e35b"

# Queues to sync (all agent inboxes)
QUEUES = ["inbox_moses", "inbox_esther", "inbox_joseph", "inbox_titus", "inbox_gisu", "inbox_kustos"]


def _fetch_moses(queue: str) -> dict | None:
    """Read (dequeue) a message from Moses' bus. Returns None if empty."""
    import base64
    payload = json.dumps({"queue": queue, "vt": 0}).encode()
    encoded = base64.b64encode(MOSES_AUTH.encode()).decode()
    req = urllib.request.Request(
        f"{MOSES_URL}/api/pgmq/read",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            if data.get("msg_id"):
                return data
            return None
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return None


def _forward_local(msg: dict) -> bool:
    """Forward a message to my local bus. Returns True on success."""
    body = msg.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass
    payload = json.dumps({
        "queue": msg["queue"],
        "message": body,
    }).encode()
    req = urllib.request.Request(
        f"{LOCAL_URL}/api/pgmq/send",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LOCAL_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return False


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"seen": [], "total_forwarded": 0}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    state = _load_state()
    seen = set(state.get("seen", []))
    total = state.get("total_forwarded", 0)
    forwarded = []
    errors = []

    for queue in QUEUES:
        # Read up to 5 messages per queue per tick
        for _ in range(5):
            msg = _fetch_moses(queue)
            if msg is None:
                break
            msg_id = msg["msg_id"]
            if msg_id in seen:
                continue
            if _forward_local(msg):
                seen.add(msg_id)
                forwarded.append(f"{queue}/{msg_id[:8]}")
                total += 1
            else:
                errors.append(f"{queue}/{msg_id[:8]}")
                break  # Stop trying this queue if local bus is down

    state["seen"] = list(seen)
    state["total_forwarded"] = total
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    # Output — no_agent cron delivers non-empty stdout
    output = []
    if forwarded:
        output.append(f"📤 Forwarded {len(forwarded)} message(s) to local bus:")
        for f in forwarded:
            output.append(f"  • {f}")
    if errors:
        output.append(f"❌ {len(errors)} message(s) failed to forward")

    if output:
        print("\n".join(output))


if __name__ == "__main__":
    main()
