#!/usr/bin/env python3
"""clean-health-queue.py — Drain old health pings from inbox_health_check.

no_agent watchdog pattern:
  Empty stdout → silent (nothing to clean)
  Text output  → delivered (count of cleaned pings)

Runs every 10 minutes via cron. Uses cortex_bus library for proper
auth (Basic/Bearer) and bus URL resolution (CORTEX_BUS_URL with
fallback). Reads/archives up to 50 messages per tick.

While draining, persists each agent's latest health vector + timestamp to
``~/.hermes-cortex/state/inbox-health-state.json`` — the hourly
``orch-health-report`` reads this file for inbox-method agents (the retired
file-inbox API is gone; the queue itself is transient and drained here).
Also updates ``last-seen.json`` so laptop grace periods work.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
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

STATE_DIR = Path.home() / ".hermes-cortex" / "state"
HEALTH_STATE_FILE = STATE_DIR / "inbox-health-state.json"
LAST_SEEN_FILE = STATE_DIR / "last-seen.json"


def _persist(agent: str, vector: list, ts: str) -> None:
    """Merge the latest health vector for one agent into the state file."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state = {}
        if HEALTH_STATE_FILE.exists():
            try:
                state = json.loads(HEALTH_STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                state = {}
        state[agent] = {"vector": vector, "ts": ts}
        HEALTH_STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        pass  # state persistence is best-effort — archiving already happened


def _record_last_seen(agent: str, ts: str) -> None:
    """Persist the agent's last-seen timestamp (laptop grace period)."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        seen = {}
        if LAST_SEEN_FILE.exists():
            try:
                seen = json.loads(LAST_SEEN_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                seen = {}
        seen[agent] = ts
        LAST_SEEN_FILE.write_text(json.dumps(seen, indent=2))
    except OSError:
        pass


def main():
    cleaned = 0
    for _ in range(MAX_PER_TICK):
        msg = bus_read(QUEUE, vt=60)
        if not msg or not msg.get("msg_id"):
            break  # queue empty or unreachable
        msg_id = msg["msg_id"]
        body = msg.get("body", {})
        if isinstance(body, dict):
            sender = (body.get("from") or "").strip().lower()
            inner = body.get("body", "")
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except (json.JSONDecodeError, TypeError):
                    inner = {}
            if sender and isinstance(inner, dict) and isinstance(inner.get("v"), list):
                ts = msg.get("enqueued_at") or datetime.now(timezone.utc).isoformat()
                _persist(sender, inner["v"], ts)
                _record_last_seen(sender, ts)
        if bus_archive(QUEUE, msg_id):
            cleaned += 1
        else:
            break  # archive failed, stop

    if cleaned:
        if cleaned >= MAX_PER_TICK:
            print(f"⚠️ Health queue overflow: archived {cleaned} pings (hit max per tick)",
                  file=sys.stderr)
        # else: silent — routine cleanup


if __name__ == "__main__":
    main()
