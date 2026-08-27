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

from state_tracker import StateTracker
from hermes_tz import format_timestamp


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = format_timestamp("[%Y-%m-%d %H:%M %Z]")
    return f"{kst} {name}:"


DB_PATH = os.path.expanduser("~/.hermes-cortex/data/loop-governance.db")
COST_DB = os.path.expanduser("~/.hermes/cron/cron-costs.db")
THRESHOLDS = {
    # hour: minimum cycles expected by that time
    14: 1,  # by 2pm: at least 1 change scored
    20: 2,  # by 8pm: at least 2 changes scored
}
COST_WARNING_DAILY = 0.75  # $0.75/day triggers cost alert


def main():
    if not os.path.exists(DB_PATH):
        print(f"{_cron_ts('scoring-activity-watchdog')} DB not found at {DB_PATH}")
        return 1

    now = datetime.now()
    hour = now.hour

    # Skip check before first threshold hour
    min_hour = min(THRESHOLDS.keys())
    if hour < min_hour:
        return 0

    # DB timestamps are UTC — use a rolling 24h window instead of calendar-day
    # boundary so KST-morning cycles (which are UTC "yesterday") are counted
    yesterday_utc = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= ?",
        (yesterday_utc,)
    )
    count = cur.fetchone()[0]
    conn.close()

    # Find applicable threshold
    expected = 0
    for thr_hour in sorted(THRESHOLDS.keys()):
        if hour >= thr_hour:
            expected = THRESHOLDS[thr_hour]

    # Weekend grace: skip alert on Saturday/Sunday — low activity is expected
    if now.weekday() >= 5:
        expected = 0

    if count < expected:
        msg = (
            f"{_cron_ts('scoring-activity-watchdog')} ⚠️  Scoring activity low: {count} cycle(s) today "
            f"(expected ≥{expected} by {hour:02d}:00). "
            f"Recent changes may be un-scored."
        )
        # Dedup (2026-08-20): don't re-deliver the identical alert on both
        # daily runs while activity stays low — fire only when it changes.
        if StateTracker("scoring-activity").evaluate(msg, has_issues=True) != "silent":
            print(msg)
            return 1
        return 0  # duplicate — silent (empty stdout, exit 0, NOT an error alert)

    # Silent on healthy
    alerts = []

    # ── Cost check ──────────────────────────────────────────
    if os.path.exists(COST_DB):
        try:
            conn = sqlite3.connect(COST_DB)
            today = datetime.now().date().isoformat()
            cur = conn.execute(
                "SELECT SUM(estimated_cost_usd) FROM cron_runs WHERE run_time >= ?",
                (today,)
            )
            row = cur.fetchone()
            daily_cost = row[0] if row and row[0] else 0.0
            conn.close()
            if daily_cost > COST_WARNING_DAILY:
                alerts.append(
                    f"⚠️  Daily cron cost ${daily_cost:.4f} exceeds ${COST_WARNING_DAILY:.2f} threshold. "
                    f"Check ~/.hermes/cron/cron-costs.db for details."
                )
        except Exception as e:
            alerts.append(f"⚠️  Cost DB check failed: {e}")

    # ── Trace quality from Langfuse ─────────────────────────
    try:
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            pk = sk = ""
            with open(env_path) as f:
                for line in f:
                    if line.startswith("HERMES_LANGFUSE_PUBLIC_KEY="):
                        pk = line.strip().split("=", 1)[1]
                    elif line.startswith("HERMES_LANGFUSE_SECRET_KEY="):
                        sk = line.strip().split("=", 1)[1]
            if pk and sk and "..." not in sk:
                import urllib.request, urllib.error, json, base64
                auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
                # Langfuse v3 rejects naive/offset fromTimestamp with HTTP 400 —
                # must be UTC with 'Z' suffix (2026-08-27).
                since = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
                req = urllib.request.Request(
                    f"http://localhost:3000/api/public/scores"
                    f"?fromTimestamp={since}&name=overall&limit=50"
                )
                req.add_header("Authorization", f"Basic {auth}")
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        scores_data = json.loads(resp.read())
                    low_scores = set()
                    for s in scores_data.get("data", []):
                        val = s.get("value", 10)
                        if isinstance(val, (int, float)) and val < 4.0:
                            low_scores.add(s.get("traceId", "?"))
                    if low_scores:
                        alerts.append(
                            f"⚠️  {len(low_scores)} trace(s) scored below 4.0 in the last 48h. "
                            f"Check Langfuse for details."
                        )
                except Exception:
                    print("expected — silently handled", file=sys.stderr)
    except Exception:
        print("expected — silently handled", file=sys.stderr)

    if alerts:
        ts = _cron_ts("scoring-activity-watchdog")
        msg = f"{ts} {' '.join(alerts)}"
        # Dedup: identical alert text stays silent on repeat runs.
        if StateTracker("scoring-activity").evaluate(msg, has_issues=True) != "silent":
            print(msg)
            return 1
        return 0

    # Healthy — clear prior alert state so a later identical alert re-fires.
    StateTracker("scoring-activity").evaluate("healthy", has_issues=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
