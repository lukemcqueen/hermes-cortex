#!/usr/bin/env python3
"""Scoring activity watchdog — no_agent cron.

Checks the loop-governance DB for cycles logged today and alerts if
activity is below expected thresholds. Silent when healthy.

Exit 0 (no stdout) = all good. Non-zero exit or stdout = alert.
"""

import sqlite3
import os
import sys
from datetime import datetime, timezone, timedelta


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = datetime.now(timezone(timedelta(hours=9))).strftime(
        "[%Y-%m-%d %H:%M KST]"
    )
    return f"{kst} {name}:"


DB_PATH = os.path.expanduser("~/.hermes/data/loop-governance.db")
THRESHOLDS = {
    # hour: minimum cycles expected by that time
    14: 1,  # by 2pm: at least 1 change scored
    20: 2,  # by 8pm: at least 2 changes scored
}


def main():
    if not os.path.exists(DB_PATH):
        print(f"{_cron_ts('scoring-activity-watchdog')} DB not found at {DB_PATH}")
        return 1

    now = datetime.now()
    today = now.date().isoformat()
    hour = now.hour

    # Skip check before first threshold hour
    min_hour = min(THRESHOLDS.keys())
    if hour < min_hour:
        return 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= ?",
        (today,)
    )
    count = cur.fetchone()[0]
    conn.close()

    # Find applicable threshold
    expected = 0
    for thr_hour in sorted(THRESHOLDS.keys()):
        if hour >= thr_hour:
            expected = THRESHOLDS[thr_hour]

    if count < expected:
        print(
            f"{_cron_ts('scoring-activity-watchdog')} ⚠️  Scoring activity low: {count} cycle(s) today "
            f"(expected ≥{expected} by {hour:02d}:00). "
            f"Recent changes may be un-scored."
        )
        return 1

    # Silent on healthy
    return 0


if __name__ == "__main__":
    sys.exit(main())