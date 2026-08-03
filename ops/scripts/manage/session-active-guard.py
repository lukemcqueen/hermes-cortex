#!/usr/bin/env python3
"""Session-active guard for day-time cron jobs.

Prints ACTIVE when an interactive session (telegram/cli) has been active
within the last SESSION_GUARD_IDLE_MIN minutes, IDLE otherwise. The output
is injected into LLM-driven cron prompts, which are instructed to skip the
tick when ACTIVE — preventing concurrent-session collisions on the shared
repo (git resets, index fights, governance-lock churn observed 2026-08-03
when agent-*-workday crons ran during an interactive session).

Designed to fail OPEN (IDLE) when the DB is missing or unreadable so a
broken guard never silently starves the fleet's day crons.
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

IDLE_MIN = int(os.environ.get("SESSION_GUARD_IDLE_MIN", "30"))
# Interactive sources — cron/bg/subagent-of-cron sessions must NOT count.
# subagent sessions run under an interactive parent when spawned from one,
# so their activity implies an active interactive session.
INTERACTIVE_SOURCES = ("telegram", "cli", "subagent")

# HERMES_HOME override for tests; default to the real state db.
_home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
db_path = _home / "state.db"


def main() -> int:
    if not db_path.exists():
        print(f"IDLE (no state.db at {db_path})")
        return 0

    cutoff = time.time() - IDLE_MIN * 60
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in INTERACTIVE_SOURCES)
        cur.execute(
            f"SELECT COUNT(*) FROM sessions "
            f"WHERE source IN ({placeholders}) AND last_activity_at > ?",
            (*INTERACTIVE_SOURCES, cutoff),
        )
        count = int(cur.fetchone()[0])
        conn.close()
    except Exception as exc:  # fail open
        print(f"IDLE (guard error: {exc})")
        return 0

    if count > 0:
        print(f"ACTIVE ({count} interactive session(s) active in last {IDLE_MIN}m)")
    else:
        print(f"IDLE (no interactive session active in last {IDLE_MIN}m)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
