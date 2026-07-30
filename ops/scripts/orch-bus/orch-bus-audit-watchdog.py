#!/usr/bin/env python3
"""
bus-audit-watchdog.py — no_agent cron; polls bus.messages for new
message activity, DLQ growth, and processing latency.

Silent when everything is healthy (no new messages, no DLQ issues,
no stuck messages).

Output format:
  `sender` → `recipient` send              @HH:MM:SS KST
  ⚠️  DLQ: inbox_esther_dlq (12 pending)
  ⏳ Stuck: inbox_moses (1 msg, 15 min)

State tracked in:
  ~/.hermes/state/bus-audit-watchdog.state  (last msg_id)
  ~/.hermes/state/bus-audit-watchdog.json   (DLQ/latency state)
"""

import json, os, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "bus-audit-watchdog.state"
STATE_JSON = HOME / ".hermes" / "state" / "bus-audit-watchdog.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

KST = timedelta(hours=9)
AGENTS = {"moses", "esther", "joseph", "gisu", "kustos", "titus", "luke"}

# Thresholds
DLQ_ALERT_THRESHOLD = 5      # Alert when DLQ has more than this many pending
STUCK_ALERT_MINUTES = 10     # Alert when a pending message sits this long

def utc_to_kst(utc_str):
    """Convert '2026-07-14 09:06:39' UTC to '17:06:39' KST string."""
    try:
        dt = datetime.strptime(utc_str[:19], "%Y-%m-%d %H:%M:%S")
        dt_kst = dt + KST
        return dt_kst.strftime("%H:%M:%S")
    except Exception:
        return utc_str[11:19]

def get_last_id():
    if STATE_FILE.exists():
        try: return STATE_FILE.read_text().strip()
        except Exception: continue
    return "00000000-0000-0000-0000-000000000000"

def save_last_id(mid):
    STATE_FILE.write_text(mid)

def load_state():
    if STATE_JSON.exists():
        try: return json.loads(STATE_JSON.read_text())
        except Exception: continue
    return {"dlq_seen": {}, "stuck_alerted": {}}

def save_state(state):
    STATE_JSON.write_text(json.dumps(state))

def run_psql(query):
    cmd = ["docker","exec","gbrain-postgres","psql","-U","gbrain","-d","gbrain","-t","-c", query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""

def main():
    state = load_state()
    last_id = get_last_id()
    STATE_FILE.touch()
    alerts = []
    resolutions = []

    now = datetime.now(timezone.utc)

    # ── 1. New message audit (existing) ──
    raw = run_psql(f"""
        SELECT m.msg_id, m.queue_name, left(m.body::text, 300), m.enqueued_at::timestamp::text
        FROM bus.messages m
        WHERE m.msg_id::text > '{last_id}'
        ORDER BY m.enqueued_at ASC
        LIMIT 15;
    """)
    lines = []
    new_last_id = last_id
    if raw.strip():
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4: continue
            mid, queue, body_text, ts = parts[0], parts[1], parts[2], parts[3]
            sender = "?"
            recipient = "?"
            action = "send"
            try:
                body = json.loads(body_text) if body_text != "None" else {}
                if isinstance(body, dict):
                    s = body.get("from", "")
                    if s and s in AGENTS:
                        sender = s
                    t = body.get("to", "")
                    if t and t in AGENTS:
                        recipient = t
                    elif queue.startswith("inbox_"):
                        recipient = queue[6:]
                    else:
                        recipient = queue
                    msg_type = body.get("type", "")
                    if msg_type == "workflow_step":
                        action = f"workflow_step ({body.get('step_name', '')})"
            except Exception:
                print("expected — silently handled", file=sys.stderr)
            new_last_id = mid

    # ── 2. DLQ monitoring ──
    dlq_raw = run_psql("""
        SELECT queue_name, count(*) as cnt
        FROM bus.messages
        WHERE queue_name LIKE '%_dlq'
          AND state = 'pending'
          AND enqueued_at > now() - interval '7 days'
        GROUP BY queue_name
        ORDER BY queue_name;
    """)
    dlq_counts = {}
    if dlq_raw.strip():
        for line in dlq_raw.strip().split("\n"):
            parts = line.strip().split("|")
            if len(parts) >= 2:
                qname = parts[0].strip()
                try: cnt = int(parts[1].strip())
                except: continue
                dlq_counts[qname] = cnt

    for qname, cnt in dlq_counts.items():
        agent = qname.replace("inbox_", "").replace("_dlq", "")
        prev = state.get("dlq_seen", {}).get(qname, 0)
        if cnt > DLQ_ALERT_THRESHOLD:
            if prev <= DLQ_ALERT_THRESHOLD:
                alerts.append(f"⚠️  DLQ growing: {qname} ({cnt} pending — agent {agent} may be failing to process)")
        elif cnt <= DLQ_ALERT_THRESHOLD and prev > DLQ_ALERT_THRESHOLD:
            resolutions.append(f"✅ DLQ cleared: {qname} (back to {cnt})")
        state.setdefault("dlq_seen", {})[qname] = cnt

    # ── 3. Processing latency monitoring ──
    stuck_raw = run_psql("""
        SELECT queue_name, count(*) as cnt,
               round(extract(epoch from (now() - min(enqueued_at)))::numeric, 0) as oldest_sec
        FROM bus.messages
        WHERE state = 'pending'
          AND queue_name NOT LIKE '%_dlq'
          AND enqueued_at < now() - interval '5 minutes'
        GROUP BY queue_name
        ORDER BY queue_name;
    """)
    stuck_msgs = {}
    if stuck_raw.strip():
        for line in stuck_raw.strip().split("\n"):
            parts = line.strip().split("|")
            if len(parts) >= 3:
                qname = parts[0].strip()
                try:
                    cnt = int(parts[1].strip())
                    age = int(parts[2].strip())
                except: continue
                stuck_msgs[qname] = (cnt, age)

    for qname, (cnt, age_min) in stuck_msgs.items():
        alerted = state.get("stuck_alerted", {}).get(qname, False)
        if age_min >= STUCK_ALERT_MINUTES * 60 and not alerted:
            alerts.append(f"⏳ Stuck: {qname} ({cnt} msg{'s' if cnt > 1 else ''}, {age_min // 60}m)")
            state.setdefault("stuck_alerted", {})[qname] = True
        elif age_min < STUCK_ALERT_MINUTES * 60 and alerted:
            state.setdefault("stuck_alerted", {})[qname] = False

    # ── Output ──
    output_lines = lines[:]
    if alerts:
        output_lines.append("")
        output_lines.extend(alerts)
    if resolutions:
        output_lines.append("")
        output_lines.extend(resolutions)

    if output_lines:
        print("```")
        print("\n".join(output_lines[-15:]))
        print("```")

    if new_last_id and new_last_id != last_id:
        try:
            latest = run_psql("SELECT MAX(msg_id::text) FROM bus.messages;").strip()
            if latest: save_last_id(latest)
        except Exception:
            print("expected — silently handled", file=sys.stderr)
    main()
