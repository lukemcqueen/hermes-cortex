#!/usr/bin/env python3
"""Re-extract today's human messages from the Hermes sessions store.

Committed with the 2026-10-07 soul-refinement report so its claims are
verifiable by a later reviewer, not merely asserted.

Usage:  python3 extract-human-messages.py [YYYY-MM-DD]
Prints the user rows for the day and writes user_msgs.json beside itself.

Read-only: opens state.db with mode=ro + PRAGMA query_only=1. Never writes
the sessions store.
"""
import datetime
import json
import os
import sqlite3
import sys

DB = os.path.expanduser("~/.hermes/state.db")


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    start_dt = datetime.datetime.fromisoformat(day)
    start = int(start_dt.timestamp())
    end = int((start_dt + datetime.timedelta(days=1)).timestamp())

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=1")
    cur = con.execute(
        "SELECT id, session_id, role, content, timestamp FROM messages "
        "WHERE role='user' AND active=1 AND timestamp >= ? AND timestamp < ? "
        "ORDER BY timestamp",
        (start, end),
    )
    rows = cur.fetchall()

    # A "human" row has text that is not cron scaffolding or a background notice.
    SCAFFOLD = ("[IMPORTANT:", "[Cron delivery", "[INTERNAL NOTIFICATION")
    human = [
        r for r in rows
        if r[3] and not any(r[3].startswith(p) for p in SCAFFOLD)
    ]

    print(f"day={day} user_rows={len(rows)} human_rows={len(human)}")
    print(f"sessions_with_human={len({r[1] for r in human})}")
    for r in human:
        ts = datetime.datetime.fromtimestamp(r[4]).strftime("%H:%M")
        preview = (r[3] or "").replace("\n", " ")[:120]
        print(f"  [{ts}] {r[1][:8]} {preview}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_msgs.json")
    json.dump(
        [{"id": r[0], "sid": r[1], "content": r[3], "ts": r[4]} for r in rows],
        open(out, "w"),
        indent=1,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
