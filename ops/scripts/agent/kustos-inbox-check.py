#!/usr/bin/env python3
"""kustos-inbox-check.py — no_agent watchdog for production agent inbox.

Checks the Agent Inbox API (localhost:8903) for messages addressed to Kustos
or broadcast to 'all'. Produces NO output when nothing to report (watchdog
pattern — silent when healthy).

Exit codes:
  0 = healthy, no output or messages printed
  1 = error contacting inbox API

Cron setup:
  name=kustos-inbox-check
  script=kustos-inbox-check.py
  no_agent=true
  schedule=*/10 * * * *
  deliver=origin
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

INBOX_URL = os.environ.get(
    "AGENT_INBOX_URL", "http://localhost:8903"
)

INBOX_AUTH = os.environ.get("CORTEX_INBOX_AUTH", "")
if not INBOX_AUTH:
    config_path = os.path.expanduser("~/.hermes-cortex/hermes-inbox.conf")
    if os.path.exists(config_path):
        for line in open(config_path):
            line = line.strip()
            if line.startswith("CORTEX_INBOX_AUTH="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    INBOX_AUTH = val
                    break

MY_NAME = "kustos"
KST = timedelta(hours=9)


def _cron_ts() -> str:
    kst = datetime.now(timezone.utc).astimezone(timezone(KST))
    return f"[{kst.strftime('%Y-%m-%d %H:%M KST')}]"


def fetch_inbox() -> list[dict]:
    """Fetch ALL messages from the inbox API (status=all to include processed)."""
    url = f"{INBOX_URL}/api/inbox"
    req = urllib.request.Request(url)
    if INBOX_AUTH:
        req.add_header("Authorization", f"Basic {INBOX_AUTH}")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        return data.get("messages", [])
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f"{_cron_ts()} ERROR: Inbox API unreachable: {e}", file=sys.stderr)
        return []


def main():
    messages = fetch_inbox()
    if not messages:
        # If we got no messages at all, the API might be down — stay silent
        # since we can't determine relevance. The error is already on stderr.
        return

    # Filter for unread messages addressed to Kustos or broadcast
    relevant = []
    for m in messages:
        if m.get("status") != "unread":
            continue
        to_field = m.get("to", "") or ""
        if to_field.lower() in ("all", "general", MY_NAME):
            relevant.append(m)

    if not relevant:
        # Silent exit — nothing for Kustos
        return

    # Print relevant messages
    for m in relevant:
        ts = m.get("timestamp", "?")[:16].replace("T", " ")
        print(f"📬 {m.get('from','?')} → {m.get('subject','(no subject)')}")
        print(f"   {ts} | {m.get('topic','?')} | priority: {m.get('priority','normal')}")
        body = m.get("body", "")
        if body:
            # Indent body for readability
            for line in body.strip().splitlines():
                print(f"   {line}")
        print()


if __name__ == "__main__":
    main()
