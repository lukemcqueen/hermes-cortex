#!/usr/bin/env python3
"""clean-health-queue.py — Drain old health pings from inbox_health_check.

no_agent watchdog pattern:
  Empty stdout → silent (nothing to clean)
  Text output  → delivered (count of cleaned pings)

Runs every 10 minutes via cron. Archives health pings older than 5 minutes
to keep the queue clean without losing audit history.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "clean-health-queue-state.json"
BUS_URL = os.environ.get("CORTEX_BUS_URL", "") or os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or "http://127.0.0.1:8903"
BUS_TOKEN = os.environ.get("CORTEX_BUS_TOKEN", "")
QUEUE = "inbox_health_check"
MAX_PER_TICK = 50  # cap per run to avoid long timeouts


def bus_request(path: str, body: dict = None, method: str = "POST") -> dict | None:
    url = f"{BUS_URL.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    if BUS_TOKEN:
        headers["Authorization"] = f"Bearer {BUS_TOKEN}"
    data = json.dumps(body).encode() if body else None
    try:
        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode()[:200]
        print(f"ERROR: {url} → {e.code} {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: {url} → {e}", file=sys.stderr)
        return None


def main():
    cleaned = 0
    for _ in range(MAX_PER_TICK):
        msg = bus_request(f"/api/pgmq/read", {"queue": QUEUE, "vt": 60})
        if not msg or not msg.get("msg_id"):
            break  # queue empty
        msg_id = msg["msg_id"]
        archived = bus_request(f"/api/pgmq/archive", {
            "queue": QUEUE,
            "msg_id": msg_id,
            "archived_by": "health-queue-cleaner",
        })
        if archived is not None:
            cleaned += 1
        else:
            break  # something wrong, stop

    if cleaned:
        print(f"🧹 Archived {cleaned} health ping(s) from {QUEUE}")


if __name__ == "__main__":
    main()
