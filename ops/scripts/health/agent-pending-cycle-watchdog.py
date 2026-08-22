#!/usr/bin/env python3
"""agent-pending-cycle-watchdog.py — no_agent watchdog: PENDING-cycle leak detection.

O5-S1 (HC gaps party 2026-08-21, roadmap F-008): scheduled PENDING-cycle
watchdog assigned to the loop-governance seam. Mirrors the on-demand logic
in cortex_doctor/checks.py (single source of truth for the leak rules) so a
governance leak is caught every 6h even when no commit/doctor run happens.

Watchdog pattern (state-transition gate):
  Empty stdout  → silent (no leaks, or unchanged since last alert)
  Text output   → delivered to user (new/changed leak found or auto-resolved)

Rules (identical to cortex_doctor/checks.py PENDING-cycles check):
  1. A PENDING cycle whose task_id has NO active .governance-*.json lock is a
     LEAK — begin_change was called but feedback_accept never ran.
  2. A PENDING cycle whose task_id holds a live lock is the CURRENT task —
     expected mid-session, INFO only.
  3. PENDING cycles older than 24h are auto-resolved to MOVE_ON (abandoned
     sessions) with a note, matching the doctor's health-check behaviour.

Usage:
  python3 agent-pending-cycle-watchdog.py          # check + auto-resolve stale
  PENDING_DB_PATH=... python3 agent-pending-cycle-watchdog.py   # custom DB

Exit codes: 0 = silent/clean (or auto-resolved with no NEW leak), 1 = alert.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from state_tracker import StateTracker
from hermes_tz import format_timestamp

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".hermes-cortex")))
DB_PATH = Path(os.environ.get("PENDING_DB_PATH", str(CORTEX_HOME / "data" / "loop-governance.db")))
STATE_DIR = CORTEX_HOME / "state"
STALE_SECONDS = 86400  # 24h — same threshold as the doctor
TERMINAL_STATES = {"completed", "cancelled"}


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = format_timestamp("[%Y-%m-%d %H:%M %Z]")
    return f"{kst} {name}:"


def _active_tasks() -> set[str]:
    """Task ids with a live (non-terminal) governance lock file."""
    active: set[str] = set()
    if not STATE_DIR.is_dir():
        return active
    for lf in STATE_DIR.glob(".governance-*.json"):
        try:
            ld = json.loads(lf.read_text())
            if ld.get("task_id") and ld.get("status") not in TERMINAL_STATES:
                active.add(ld["task_id"])
        except (OSError, ValueError):
            # Never delete/interpret what we can't parse — it is being written
            # (P1-A lock-lifecycle lesson). Skip unreadable locks.
            continue
    return active


def main() -> int:
    if not DB_PATH.exists():
        print(f"{_cron_ts('pending-cycle-watchdog')} loop-governance DB not found at {DB_PATH}")
        return 1

    now = datetime.now()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    pending = conn.execute(
        "SELECT id, task_id, cycle_num, session_id, timestamp FROM loop_cycles "
        "WHERE decision='PENDING' LIMIT 5000"
    ).fetchall()

    if not pending:
        conn.close()
        return 0  # clean — silent

    active = _active_tasks()
    stale_count = 0
    fresh: list[sqlite3.Row] = []
    for r in pending:
        try:
            ts = datetime.fromisoformat(str(r["timestamp"]).replace("Z", ""))
        except (ValueError, TypeError):
            ts = now - timedelta(days=7)
        if (now - ts).total_seconds() > STALE_SECONDS:
            conn.execute(
                "UPDATE loop_cycles SET decision='MOVE_ON', "
                "outcome_note='auto-resolved by pending-cycle watchdog — >24h stale' "
                "WHERE id=?",
                (r["id"],),
            )
            stale_count += 1
        else:
            fresh.append(r)
    conn.commit()

    current = [r for r in fresh if r["task_id"] in active]
    leaked = [r for r in fresh if r["task_id"] not in active]

    lines: list[str] = []
    if stale_count:
        lines.append(f"auto-resolved {stale_count} stale PENDING cycle(s) >24h old (abandoned sessions)")
    if leaked:
        for r in leaked[:5]:
            sid = (r["session_id"] or "unknown")[:12]
            lines.append(
                f"LEAK: {r['task_id']}#{r['cycle_num']} (session {sid}) — "
                f"begin_change ran but never scored; no live lock"
            )
        if len(leaked) > 5:
            lines.append(f"…and {len(leaked) - 5} more leak(s)")
    if current:
        # Current-task cycles are expected mid-session — INFO, not an alert.
        # Mention only when we are also alerting, so a healthy session never
        # generates delivery.
        pass

    conn.close()

    if not lines:
        return 0  # only current-task cycles — healthy, silent

    msg = "\n".join(lines)
    # State-transition gate: fire only when the leak fingerprint changes.
    fp = "|".join(sorted(f"{r['task_id']}#{r['cycle_num']}" for r in leaked)) or "none"
    fp += f"|stale={stale_count}"
    action = StateTracker("pending-cycle-watchdog").evaluate(fp, has_issues=bool(leaked))
    if action == "silent":
        return 0

    print(f"{_cron_ts('pending-cycle-watchdog')} {msg}")
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
