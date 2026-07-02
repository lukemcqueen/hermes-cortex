#!/usr/bin/env python3
"""inbox-flag.py — Companion script for agent-inbox (LLM cron).

Runs every 10m as a no_agent watchdog. Checks the agent inbox directory
for new messages addressed to Moses. Silent when nothing new.

Output shape (new messages found):
{
  "has_work": true,
  "unread_count": 3,
  "messages": [
    {"from": "titus", "subject": "health", "timestamp": "2026-07-02T11:05:00", "filename": "20260702110531820148-titus.md"},
  ],
  "last_check": "2026-07-02T11:10:00+09:00"
}

Output when nothing new: empty (silent = no delivery needed).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HOME = Path.home()
INBOX_DIR = HOME / "agent-inbox-private" / "inbox"
STATE_DIR = HOME / ".hermes" / "state"
SEEN_FILE = STATE_DIR / "inbox-flag-seen"

KST = timezone(timedelta(hours=9))


def get_kst_now() -> str:
    return datetime.now(KST).isoformat()


def load_seen_ids() -> set[str]:
    if SEEN_FILE.exists():
        return {line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip()}
    return set()


def save_seen_ids(ids: set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text("\n".join(sorted(ids)) + "\n")


def main() -> int:
    seen = load_seen_ids()

    if not INBOX_DIR.exists():
        return 1

    # Find all message files addressed to Moses
    new_messages = []
    for f in sorted(INBOX_DIR.iterdir()):
        if not f.name.endswith(".md"):
            continue
        # Filename pattern: <timestamp>-<recipient>.md
        # Messages for Moses end with -moses.md
        if not f.name.rstrip(".md").endswith("-moses"):
            # Also check inbox messages that might use the "to" field for moses
            # But primarily rely on filename suffix
            continue

        if f.name in seen:
            continue

        # Parse basic info from the message file
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Extract YAML-like fields
        msg_from = "unknown"
        msg_subject = "unknown"
        msg_time = ""
        match_to = re.search(r"^\s*to:\s*(.+)$", content, re.MULTILINE)
        match_from = re.search(r"^\s*from:\s*(.+)$", content, re.MULTILINE)
        match_subject = re.search(r"^\s*subject:\s*(.+)$", content, re.MULTILINE)

        if match_from:
            msg_from = match_from.group(1).strip()
        if match_subject:
            msg_subject = match_subject.group(1).strip()

        # Extract timestamp from filename
        ts_match = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", f.name)
        if ts_match:
            y, mo, d, h, mi, s = ts_match.groups()
            msg_time = f"{y}-{mo}-{d}T{h}:{mi}:{s}"

        new_messages.append({
            "from": msg_from,
            "subject": msg_subject,
            "timestamp": msg_time,
            "filename": f.name,
        })

        seen.add(f.name)

    # Save seen IDs so we don't re-report
    save_seen_ids(seen)

    if not new_messages:
        # Silent — nothing to report
        return 0

    # Output structured JSON for the LLM cron
    result = {
        "has_work": True,
        "unread_count": len(new_messages),
        "messages": new_messages,
        "last_check": get_kst_now(),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
