#!/usr/bin/env python3
"""
bus-audit-watchdog.py — no_agent cron; polls bus.audit_log every 60s and
outputs new entries. Silent when no activity (watchdog pattern).

Output format per entry:
  [agent] action → queue @ HH:MM:SS

Delivered to Telegram via cron delivery.
State tracked in ~/.hermes/state/bus-audit-watchdog.state
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "bus-audit-watchdog.state"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

# Which actions to include (full list or filtered)
INCLUDE_ACTIONS = {
    "send", "read", "archive", "workflow_dispatch", "workflow_dispatched",
    "step_dispatched", "step_completed", "workflow_completed",
    "a2a_send", "a2a_receive",
}

# Which actions to SKIP (noisy — poll cycles, archives, maintenance)
EXCLUDE_ACTIONS = {
    "read", "archive", "requeue",
}

# Agents we care about
AGENTS = {"moses", "esther", "joseph", "gisu", "kustos", "titus", "luke"}


def get_last_id():
    """Read the last processed audit ID from state file."""
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def save_last_id(audit_id):
    """Persist the last processed audit ID."""
    STATE_FILE.write_text(str(audit_id))


def query_audit_since(last_id, limit=30):
    """Query bus.audit_log for entries after last_id."""
    cmd = [
        "docker", "exec", "gbrain-postgres", "psql",
        "-U", "gbrain", "-d", "gbrain", "-t",
        "-c", f"""
        SELECT id, agent_name, action, queue, detail::text,
               created_at::timestamp::text
        FROM bus.audit_log
        WHERE id > {last_id}
          AND agent_name IS NOT NULL
        ORDER BY id ASC
        LIMIT {limit};
        """
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return []
        return parse_psql_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[WATCHDOG ERROR] Query failed: {e}", file=sys.stderr)
        return []


def parse_psql_output(raw):
    """Parse psql tab-separated output into dicts."""
    rows = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("("):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        try:
            row = {
                "id": int(parts[0]),
                "agent": parts[1] if parts[1] != "None" else "?",
                "action": parts[2] if parts[2] != "None" else "?",
                "queue": parts[3] if parts[3] != "None" else "-",
                "detail": parts[4][:200] if parts[4] != "None" else "",
                "time": parts[5][11:19] if len(parts[5]) > 11 else parts[5],  # HH:MM:SS
            }
            rows.append(row)
        except (ValueError, IndexError):
            continue
    return rows


def format_entry(row):
    """Format a single audit entry for Telegram."""
    agent = row["agent"].ljust(8)
    action = row["action"].ljust(18)
    queue = row["queue"] if row["queue"] != "-" else ""
    time = row["time"]
    detail = row["detail"]

    # Extract workflow name from detail if present
    wf_name = ""
    if detail:
        try:
            d = json.loads(detail)
            wf_name = d.get("name", "") or d.get("workflow_id", "")[:8] or ""
        except (json.JSONDecodeError, TypeError):
            pass

    parts = [f"`{agent}` `{action}`"]
    if queue:
        parts.append(f"→ `{queue}`")
    if wf_name:
        parts.append(f"({wf_name})")
    parts.append(f"@{time}")
    return " ".join(parts)


def main():
    last_id = get_last_id()
    rows = query_audit_since(last_id)

    if not rows:
        return  # Silent — no new activity

    # Filter to relevant actions
    filtered = [r for r in rows if r["action"] not in EXCLUDE_ACTIONS]

    if not filtered:
        # Still update state so we don't re-read these
        save_last_id(rows[-1]["id"])
        return

    lines = ["```"]
    for row in filtered:
        lines.append(format_entry(row))
    lines.append("```")

    # Save state at the last row we saw
    save_last_id(rows[-1]["id"])

    # Print for cron delivery
    print("\n".join(lines))


if __name__ == "__main__":
    main()
