#!/usr/bin/env python3
"""
bus-audit-watchdog.py — no_agent cron; polls bus.messages for new
message activity. Silent when no new messages.

Output format:
  `sender` → `recipient` send              @HH:MM:SS KST
  `sender` → `recipient` workflow_step(name) @HH:MM:SS KST

State tracked in ~/.hermes/state/bus-audit-watchdog.state
"""

import json, os, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "bus-audit-watchdog.state"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

KST = timedelta(hours=9)

AGENTS = {"moses", "esther", "joseph", "gisu", "kustos", "titus", "luke"}

def utc_to_kst(utc_str):
    """Convert '2026-07-14 09:06:39' UTC to '17:06:39' KST string."""
    try:
        dt = datetime.strptime(utc_str[:19], "%Y-%m-%d %H:%M:%S")
        dt_kst = dt + KST
        return dt_kst.strftime("%H:%M:%S")
    except:
        return utc_str[11:19]

def get_last_id():
    if STATE_FILE.exists():
        try: return STATE_FILE.read_text().strip()
        except: pass
    return "00000000-0000-0000-0000-000000000000"

def save_last_id(mid):
    STATE_FILE.write_text(mid)

def run_psql(query):
    cmd = ["docker","exec","gbrain-postgres","psql","-U","gbrain","-d","gbrain","-t","-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""

def main():
    last_id = get_last_id()
    STATE_FILE.touch()  # update mtime every tick — system-alert-watchdog checks freshness

    raw = run_psql(f"""
        SELECT m.msg_id, m.queue_name, left(m.body::text, 300), m.enqueued_at::timestamp::text
        FROM bus.messages m
        WHERE m.msg_id::text > '{last_id}'
        ORDER BY m.enqueued_at ASC
        LIMIT 15;
    """)
    if not raw.strip():
        return

    lines = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line: continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4: continue
        mid, queue, body_text, ts = parts[0], parts[1], parts[2], parts[3]

        # Parse body
        sender = "?"
        recipient = "?"
        action = "send"
        step_info = ""
        try:
            body = json.loads(body_text) if body_text != "None" else {}
            if isinstance(body, dict):
                s = body.get("from", "")
                if s and s in AGENTS:
                    sender = s
                # Extract recipient from queue name or body.to
                t = body.get("to", "")
                if t and t in AGENTS:
                    recipient = t
                elif queue.startswith("inbox_"):
                    recipient = queue[6:]  # strip "inbox_"
                else:
                    recipient = queue

                # Workflow step info
                msg_type = body.get("type", "")
                if msg_type == "workflow_step":
                    step_name = body.get("step_name", "")
                    wf_id = body.get("workflow_id", "")[:8]
                    step_info = f" ({step_name})"
                    action = f"workflow_step{step_info}"
        except:
            pass

        time_kst = utc_to_kst(ts)
        lines.append(f"`{sender}` → `{recipient}` `{action}` @{time_kst} KST")
        last_id = mid

    if not lines:
        return

    try:
        latest = run_psql("SELECT MAX(msg_id::text) FROM bus.messages;").strip()
        if latest: save_last_id(latest)
    except:
        pass

    print("```")
    print("\n".join(lines[-10:]))
    print("```")

if __name__ == "__main__":
    main()
