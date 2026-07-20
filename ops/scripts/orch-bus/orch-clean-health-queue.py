#!/usr/bin/env python3
"""clean-health-queue.py — Drain old health pings from inbox_health_check.

no_agent watchdog pattern:
  Empty stdout → silent (nothing to clean)
  Text output  → delivered (count of cleaned pings)

Runs every 10 minutes via cron. Uses cortex_bus library for proper
auth (Basic/Bearer) and bus URL resolution (CORTEX_BUS_URL with
fallback). Reads/archives up to 50 messages per tick.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_VAR = os.environ.get("CORTEX_REPO", "")
REPO = Path(REPO_VAR) if REPO_VAR else Path()
if not REPO.is_dir() or not REPO_VAR:
    for c in [Path.home() / "hermes-cortex", Path.home() / "src" / "hermes-cortex"]:
        if c.is_dir() and (c / "AGENTS.md").exists():
            REPO = c
            break

from hermes_paths import ensure_scripts_path
ensure_scripts_path()
from lib.cortex_bus import bus_read, bus_archive

QUEUE = "inbox_health_check"
MAX_PER_TICK = 50


def main():
    cleaned = 0
    for _ in range(MAX_PER_TICK):
        msg = bus_read(QUEUE, vt=60)
        if not msg or not msg.get("msg_id"):
            break  # queue empty or unreachable
        msg_id = msg["msg_id"]
        if bus_archive(QUEUE, msg_id):
            cleaned += 1
        else:
            break  # archive failed, stop

    if cleaned:
        print(f"🧹 Archived {cleaned} health ping(s) from {QUEUE}")


if __name__ == "__main__":
    main()
