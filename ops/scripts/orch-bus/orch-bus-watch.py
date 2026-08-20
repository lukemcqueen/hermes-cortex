#!/usr/bin/env python3
"""
Agent Bus inbox watch — no_agent cron pattern.

Queries all agent queues and outputs formatted summaries
when messages are waiting. Silent when empty (watchdog pattern).

Usage as no_agent cron:
    hermes cron create name=bus-inbox-watch schedule="*/10 * * * *" \\
      script=bus-watch.py no_agent=true deliver=origin
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from hermes_tz import format_timestamp

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cortex_bus.queue import get_queue, NotAvailableError


def main():
    try:
        bus = get_queue()
    except NotAvailableError:
        print("expected — silently handled", file=sys.stderr)
        sys.exit(0)
    
    try:
        queues = bus.list_queues()
    except Exception:
        print("expected — silently handled", file=sys.stderr)
        sys.exit(0)
    
    # Find queues with pending messages (exclude DLQs from main output)
    active = [q for q in queues if q["depth"] > 0 and not q["dlq"]]
    dlq_active = [q for q in queues if q["depth"] > 0 and q["dlq"]]
    
    if not active and not dlq_active:
        # Silent — watchdog pattern
        sys.exit(0)
    
    now = format_timestamp("%Y-%m-%d %H:%M %Z")
    print(f"━━━ Agent Bus — {now} ━━━")
    
    if active:
        print(f"\n📬 Inbox messages:")
        for q in active:
            print(f"  {q['name']}: {q['depth']} pending")
    
    if dlq_active:
        print(f"\n⚠️  Dead letter queues:")
        for q in dlq_active:
            print(f"  {q['name']}: {q['depth']} messages (failed 3+ times)")
    
    # Summary line
    total = sum(q["depth"] for q in active) + sum(q["depth"] for q in dlq_active)
    print(f"\nTotal: {total} messages across {len(active) + len(dlq_active)} queues")


if __name__ == "__main__":
    main()
