#!/usr/bin/env python3
"""fleet-update-check.py — check fleet agents' update progress.

Queries the LOCAL bus DB (docker exec mycortex-postgres) for evidence
that titus/joseph/kustos/gisu processed the FLEET UPDATE v2 tasks:
- consumed (archived) their update task
- sent any reply/report back (inbox_esther or their outbound)
- current queue depth (still pending = not picked up)

Output is compact — empty when nothing new (watchdog pattern).
"""
import json
import subprocess
import sys
from datetime import datetime, timezone

AGENTS = ["titus", "joseph", "kustos", "gisu"]
TASKS = {
    "titus": "abe78ba1",
    "joseph": "f9a57436",
    "kustos": "5dc477e4",
    "gisu": "3cee66bd",
}


def psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "mycortex-postgres", "psql", "-U", "mycortex",
         "-d", "mycortex", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=20)
    return r.stdout.strip()


def main() -> int:
    lines = []
    for agent in AGENTS:
        tid = TASKS[agent]
        # Still pending in queue?
        pending = psql(
            f"SELECT count(*) FROM bus.messages WHERE queue_name='inbox_{agent}' "
            f"AND body::text LIKE '%{tid}%'")
        # Consumed (archived)?
        archived = psql(
            f"SELECT count(*) FROM bus.messages_archive WHERE queue_name='inbox_{agent}' "
            f"AND body::text LIKE '%{tid}%'")
        # Any reply from this agent into esther's inbox (their report)?
        replied = psql(
            f"SELECT count(*) FROM bus.messages WHERE queue_name='inbox_esther' "
            f"AND body::text LIKE '%{agent}%' AND body::text LIKE '%update%'")
        state = "PENDING" if int(pending or 0) else ("DONE (archived)" if int(archived or 0) else "consumed/unknown")
        lines.append(f"• {agent}: task {tid[:8]} → {state} | replies-to-esther: {replied}")

    # Also: any agent-initiated outbound (they report via inbox_esther or out_*)
    out = psql(
        "SELECT queue_name, count(*) FROM bus.messages WHERE queue_name LIKE 'out_%' "
        "GROUP BY queue_name ORDER BY queue_name")
    if out:
        lines.append("outbound queues with msgs: " + out.replace("\n", "; "))

    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"⏱ fleet update check {stamp}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
