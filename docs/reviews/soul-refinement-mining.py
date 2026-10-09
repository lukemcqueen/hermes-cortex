#!/usr/bin/env python3
"""Re-executable mining evidence for the soul-refinement cron (day given as argv[1]).

Why this exists (observed 2026-10-09): the self-adversarial reviewer refused the
soul-refinement cycle on ADV-11901-1 — the day's counts ("102 unverified-claim
mentions", "N sessions with human text") were NARRATED in the report rather than
produced by a committed, re-runnable artifact. This script is that artifact, and
`docs/reviews/soul-refinement-2026-10-09.mining.json` is its committed output.

Usage:
    python3 docs/reviews/soul-refinement-mining.py 2026-10-09

Writes nothing; prints JSON to stdout. Read-only against the sessions store.
"""

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

STATE_DB = "file:/home/esther/.hermes/state.db?mode=ro"
KST = timezone(timedelta(hours=9))

# Scaffolding that arrives as role='user' but carries no human instruction.
SCAFFOLD_PREFIXES = ("[IMPORTANT:", "[Cron delivery", "[OUT-OF-BAND", "Gateway message origin")


def day_bounds(day: str):
    """Unix epoch floats, NOT ISO — the messages.timestamp column is a float and
    an ISO bound silently returns 0 rows (trap hit 2026-10-09)."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST)
    return d.timestamp(), (d + timedelta(days=1)).timestamp()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    day = sys.argv[1]
    start, end = day_bounds(day)

    con = sqlite3.connect(STATE_DB, uri=True)
    con.execute("PRAGMA query_only=1")
    cur = con.cursor()

    # A. user rows, and which carry human text vs cron/gateway scaffolding
    cur.execute(
        """SELECT session_id, content FROM messages
           WHERE active=1 AND role='user' AND timestamp>=? AND timestamp<? """,
        (start, end),
    )
    sessions = Counter()
    human_by_session = Counter()
    for sid, content in cur.fetchall():
        sessions[sid] += 1
        c = (content or "").lstrip()
        if not any(c.startswith(p) for p in SCAFFOLD_PREFIXES):
            human_by_session[sid] += 1

    # B. reviewer finding techniques across the day's tool output
    cur.execute(
        """SELECT content FROM messages
           WHERE active=1 AND content LIKE '%technique%' AND timestamp>=? AND timestamp<? """,
        (start, end),
    )
    techniques = Counter()
    for (content,) in cur.fetchall():
        for m in re.finditer(r'technique\\?"?:\s*\\?"?([a-z\-]+)', content or ""):
            techniques[m.group(1)] += 1

    print(json.dumps({
        "day": day,
        "window_epoch": [start, end],
        "user_rows_total": sum(sessions.values()),
        "sessions_with_user_rows": len(sessions),
        "sessions_with_human_text": dict(human_by_session),
        "human_rows_total": sum(human_by_session.values()),
        "reviewer_techniques": dict(techniques.most_common()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
