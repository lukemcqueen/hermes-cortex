#!/usr/bin/env python3
"""
bus-audit-watchdog.py — no_agent cron; polls bus.messages for new message
activity every 60s. Silent when no new messages (watchdog pattern).

Output per entry:
  `agent  ` send  → `queue` @ HH:MM:SS

Delivered to Telegram via cron delivery.
State tracked in ~/.hermes/state/bus-audit-watchdog.state
"""

import json, os, subprocess, sys
from pathlib import Path

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "bus-audit-watchdog.state"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

AGENTS = {"moses", "esther", "joseph", "gisu", "kustos", "titus", "luke"}

def get_last_id():
    if STATE_FILE.exists():
        try: return STATE_FILE.read_text().strip()
        except: pass
    return "00000000-0000-0000-0000-000000000000"

def save_last_id(mid):
    STATE_FILE.write_text(mid)

def run_psql(query):
    cmd = ["docker","exec","gbrain-postgres","psql","-U","gbrain","-d","gbrain","-t", "-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""

def main():
    last_id = get_last_id()

    # Get ALL new messages since last seen ID
    raw = run_psql(f"""
        SELECT m.msg_id, m.queue_name, left(m.body::text, 200), m.enqueued_at::timestamp::text
        FROM bus.messages m
        WHERE m.msg_id::text > '{last_id}'
        ORDER BY m.enqueued_at ASC
        LIMIT 15;
    """)
    if not raw.strip():
        return  # silent

    rows = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line: continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4: continue
        mid, queue, body_text, ts = parts[0], parts[1], parts[2], parts[3]

        # Extract sender from body JSON
        sender = "?"
        try:
            body = json.loads(body_text) if body_text != "None" else {}
            if isinstance(body, dict):
                s = body.get("from", "")
                if s and s in AGENTS:
                    sender = s
        except: pass

        time_str = ts[11:19] if len(ts) > 11 else ts
        rows.append(f"`{sender:<8}` `send` → `{queue}` @{time_str}")
        last_id = mid  # track the last msg_id

    if not rows:
        return

    # Save state as the last msg_id
    try:
        latest = run_psql("SELECT MAX(msg_id::text) FROM bus.messages;").strip()
        if latest: save_last_id(latest)
    except: pass

    print("```")
    print("\n".join(rows[-10:]))  # max 10 per tick
    print("```")

if __name__ == "__main__":
    main()
