#!/usr/bin/env python3
"""orch-weekly-cost-report.py — weekly fleet cost report, alerting above target.

Story c579ef95 [cost/3]: a weekly report with an alert when the fleet daily
average exceeds $10. Orchestrator-scope, no_agent, delivered to Telegram.

Rules this script exists to keep (they come from the cost stack that was removed
on 2026-10-06, whose design notes survive in
skills/devops/llm-cost-optimization/references/fleet-cost-data-sources.md):

  * spend is read from Hermes' own state.db sessions (estimated_cost_usd, written
    live at current prices) — never from a stored price table;
  * COVERAGE is printed, not implied: which hosts the number covers and which it
    does not. A report that hides missing data is worse than no report;
  * a missing source prints NO DATA and does NOT alert — an alert built on no
    data is the same defect as a zero standing in for a gap;
  * the average is over MEASURED days only, and says so.

Exit codes:
  0  report emitted, no breach (or no data — never a false alert)
  1  measured daily average is above the target: a FAILED run, deliberately, so
     the breach is machine-visible rather than a quiet line. Consequence: the
     failure watchdog pauses a job after three consecutive errors —
     ops/scripts/health/agent-cron-failure-watchdog.py:40 is
     `CONSECUTIVE_FAILURE_LIMIT = 3  # consecutive errors before alert + pause`.
     Three consecutive breaches therefore leave this job PAUSED, which is itself
     the escalation signal and shows up in the cron list rather than being
     silently absorbed. The proof of that threshold travels with the claim:
     docs/evidence/cost3-per-cron-cost-metrics/verify.txt section 5 prints the
     `grep -n CONSECUTIVE_FAILURE_LIMIT` output with the line numbers, because the
     watchdog file itself is outside this change's range. (Finding ADV-13655-1 on
     cycle 13655: the first version asserted the pause without any pointer.)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_AUDIT = Path.home() / ".hermes" / "cron" / "usage_audit.jsonl"
DEFAULT_STATE_DB = Path.home() / ".hermes" / "state.db"
DEFAULT_TARGET_USD = 10.0

UNMEASURED = ("not measured: the four worker hosts (each needs its own local adapter — "
              "fleet cost coverage [cost/4]). The baseline that established this gap is "
              "docs/evidence/cost-baseline-2026-10-19.txt (section 6: 2 of 6 hosts measured). "
              "This average covers the measured hosts only.")


def read_tokens_by_job(path: Path):
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None, None
    tokens: dict[str, float] = defaultdict(float)
    fires: dict[str, int] = defaultdict(int)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        job = row.get("job_id")
        if not isinstance(job, str) or not job:
            continue
        fires[job] += 1
        try:
            tokens[job] += float(row.get("total_tokens") or 0)
        except (TypeError, ValueError):
            pass
    return tokens, fires


def read_cost_by_day(db_path: Path, days: int):
    """Return ({utc_date: usd}, note) — usd None-able when the source is unreadable."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    try:
        con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        return None, f"state.db unreadable ({exc})"
    try:
        rows = con.execute(
            "SELECT started_at, estimated_cost_usd FROM sessions"
            " WHERE source = 'cron' AND started_at >= ?",
            (cutoff,),
        ).fetchall()
    except sqlite3.Error as exc:
        return None, f"sessions table unreadable ({exc})"
    finally:
        con.close()
    per_day: dict[str, float] = defaultdict(float)
    for started_at, cost in rows:
        try:
            day = datetime.fromtimestamp(float(started_at), timezone.utc).date().isoformat()
            per_day[day] += float(cost or 0)
        except (TypeError, ValueError):
            continue
    return per_day, ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", default=str(DEFAULT_AUDIT), help="usage_audit.jsonl path")
    p.add_argument("--state-db", default=str(DEFAULT_STATE_DB), help="state.db path")
    p.add_argument("--days", type=int, default=7, help="window in days (default 7)")
    p.add_argument("--target", type=float,
                   default=float(os.environ.get("CORTEX_COST_DAILY_TARGET_USD", DEFAULT_TARGET_USD)),
                   help="fleet daily-average target in USD (default $10)")
    p.add_argument("--host", default=os.environ.get("AGENT_NAME", "this host"),
                   help="host label (default: $AGENT_NAME)")
    args = p.parse_args()

    lines: list[str] = []
    lines.append(f"💰 Weekly fleet cost report — {args.host}, window {args.days}d")

    per_day, note = read_cost_by_day(Path(args.state_db), args.days)
    avg = None
    if per_day is None:
        lines.append(f"Spend: NO DATA — {note}. No alert is raised from no data.")
    elif not per_day:
        lines.append("Spend: NO DATA — no cron sessions in the window "
                     "(nothing ran, or the rows were archived). No alert from no data.")
    else:
        lines.append("Spend by day (state.db sessions, source=cron):")
        for day in sorted(per_day):
            lines.append(f"  {day}  ${per_day[day]:.2f}")
        avg = sum(per_day.values()) / len(per_day)
        measured = "/".join(sorted(per_day))
        lines.append(f"Measured days: {len(per_day)} ({measured})")
        lines.append(f"Measured daily average: ${avg:.2f}  (target ${args.target:.2f})")
        lines.append(f"Window total: ${sum(per_day.values()):.2f}")

    tokens, fires = read_tokens_by_job(Path(args.audit))
    if tokens:
        lines.append("Top jobs by tokens (audit log, lifetime):")
        for job in sorted(tokens, key=lambda j: tokens[j], reverse=True)[:5]:
            lines.append(f"  {job}  {tokens[job]:.0f} tokens, {fires[job]} fires")
    else:
        lines.append("Tokens: NO DATA — usage_audit.jsonl unreadable.")

    lines.append("COVERAGE")
    lines.append(f"  measured: {args.host} (this host's own state.db / audit log)")
    lines.append(f"  {UNMEASURED}")

    breach = False
    if avg is not None and avg > args.target:
        breach = True
        lines.insert(1, f"⚠️ FLEET COST ABOVE TARGET — measured daily average ${avg:.2f}"
                        f" > ${args.target:.2f}")

    print("\n".join(lines))
    return 1 if breach else 0


if __name__ == "__main__":
    sys.exit(main())
