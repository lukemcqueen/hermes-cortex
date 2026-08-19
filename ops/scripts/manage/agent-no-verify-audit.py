#!/usr/bin/env python3
"""no-verify-audit — watchdog for --no-verify events + bypass debt.

Watchdog pattern: empty stdout = silent (nothing to report).
Prints when:
  • new --no-verify events appear since last check
  • bypass-debt >= 4 (escape hatch EXHAUSTED — 4th bypass mandated)
  • scoring backlog: PENDING/unscored governance cycles accumulate

Dedup (2026-08-20): each section fires only when its CONTENT changes —
the same backlog or debt across ticks stays silent, so an unchanged
reminder posts ONCE, not every 10 minutes.

State tracked in: ~/.hermes-cortex/state/no-verify-audit-state.json
Debt tracked in:  ~/.hermes-cortex/state/bypass-debt.json
Schedule: every 10 minutes (2026-08-05 — was 60m; bounded escape hatch).
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

LOG_FILE = os.path.expanduser("~/.hermes-cortex/state/no-verify-log.json")
STATE_FILE = os.path.expanduser("~/.hermes-cortex/state/no-verify-audit-state.json")
DEBT_FILE = os.path.expanduser("~/.hermes-cortex/state/bypass-debt.json")
LOOP_DB = os.path.expanduser("~/.hermes-cortex/data/loop-governance.db")

# Scoring backlog: alert when >= 2 PENDING cycles and any is older than this
PENDING_MIN_AGE_MIN = 30
PENDING_ALERT_COUNT = 2


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "last_timestamp": None,
        "last_index": -1,
        "last_backlog": [],
        "last_debt": 0,
    }


def save_state(state):
    if state is None:
        state = {}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_events():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return []


def load_debt():
    if not os.path.exists(DEBT_FILE):
        return {}
    with open(DEBT_FILE) as f:
        try:
            return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}


def check_pending_cycles():
    """Return list of stale PENDING cycles (scoring backlog)."""
    if not os.path.exists(LOOP_DB):
        return []
    try:
        conn = sqlite3.connect(LOOP_DB)
        rows = conn.execute(
            "SELECT task_id, timestamp FROM loop_cycles WHERE decision='PENDING'"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    if len(rows) < PENDING_ALERT_COUNT:
        return []
    now = datetime.now(timezone.utc)
    stale = []
    for task_id, ts in rows:
        try:
            t = datetime.fromisoformat(str(ts))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age_min = (now - t).total_seconds() / 60
        except (ValueError, TypeError):
            age_min = PENDING_MIN_AGE_MIN + 1
        if age_min > PENDING_MIN_AGE_MIN:
            stale.append((task_id, ts))
    return stale


def main():
    state = load_state()
    events = load_events()
    debt = load_debt()
    lines = []
    changed = False

    # ── 1. New no-verify events ──
    new_events = []
    for i, evt in enumerate(events):
        if i > state["last_index"]:
            new_events.append(evt)

    if new_events:
        lines.append(f"⚠️  {len(new_events)} new --no-verify event(s) detected:")
        for evt in new_events:
            ts = evt.get("timestamp", "?")
            commit = evt.get("commit", "?")[:10]
            msg = evt.get("message", "?")
            lines.append(f"  • {ts}  {commit}  {msg}")
        state["last_index"] = len(events) - 1
        state["last_timestamp"] = new_events[-1].get(
            "timestamp", state["last_timestamp"]
        )
        changed = True

    # ── 2. Escape hatch exhausted (mandated 4th bypass) ──
    # Dedup: fire only when the debt value changes (or re-accumulates after a
    # reset) — an unchanged >= 4 stays silent instead of posting every tick.
    consec = debt.get("consecutive_no_verify", 0)
    if consec >= 4 and consec != state.get("last_debt"):
        lines.append(
            f"🚫  ESCAPE HATCH EXHAUSTED: {consec} consecutive --no-verify commits "
            "(bypass-debt)."
        )
        lines.append(
            "    The 4th bypass is MANDATED — pushes carrying it are blocked and "
            "--no-verify git commands are refused until a fully verified commit "
            "(no --no-verify) resets the counter."
        )
        state["last_debt"] = consec
        changed = True
    elif consec < 4 and consec != state.get("last_debt"):
        # Track the quiet baseline so a reset → re-accumulation re-fires.
        state["last_debt"] = consec
        changed = True

    # ── 3. Scoring backlog (PENDING cycles not cleared) ──
    # Dedup: fire only when the stale set CHANGES — an identical backlog across
    # ticks stays silent (2026-08-20, Luke: unchanged output posted to Telegram
    # every 10 min).
    stale = check_pending_cycles()
    backlog_sig = sorted(f"{ts}|{task_id}" for task_id, ts in stale)
    if backlog_sig and backlog_sig != state.get("last_backlog"):
        lines.append(
            f"🧾  SCORING BACKLOG: {len(stale)} PENDING governance cycle(s) older "
            f"than {PENDING_MIN_AGE_MIN} min — score them (feedback_accept/override "
            "→ end_change) so scoring stays current."
        )
        for task_id, ts in stale[:5]:
            lines.append(f"    • {ts}  {task_id[:60]}")
        state["last_backlog"] = backlog_sig
        changed = True
    elif not backlog_sig and state.get("last_backlog"):
        # Record the empty baseline silently so a later re-accumulation re-fires.
        state["last_backlog"] = []
        changed = True

    if lines:
        print("\n".join(lines))

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
