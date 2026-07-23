#!/usr/bin/env python3
"""
fleet-costs — Cost reporting CLI for Hermes Cortex.

Queries the cron-cost-tracking SQLite DB and produces per-job,
per-agent, per-week, and per-day cost summaries.

Usage:
    fleet-costs                         # Summary: last 7 days + total
    fleet-costs --days 30               # Last 30 days
    fleet-costs --weekly                # Weekly breakdown
    fleet-costs --jobs                  # Per-job breakdown
    fleet-costs --agent <name>          # Filter by agent
    fleet-costs --json                  # Machine-readable output

Exit codes:
    0 — Success
    1 — DB not found
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"
REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"


def get_db() -> sqlite3.Connection:
    if not COST_DB.exists():
        print(f"❌ Cost DB not found: {COST_DB}", file=sys.stderr)
        print("   Cost tracking may not be deployed.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(COST_DB))
    conn.row_factory = sqlite3.Row
    return conn


def load_registry() -> dict:
    """Load agent registry for budget info."""
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}


def cmd_summary(args):
    """Summary of costs."""
    db = get_db()
    days = args.days or 7
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Total all-time
    total = db.execute("SELECT SUM(estimated_cost_usd) FROM cron_runs").fetchone()[0] or 0.0

    # Recent period
    recent = db.execute(
        "SELECT SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) "
        "FROM cron_runs WHERE run_time >= ?", (cutoff,)
    ).fetchone()
    recent_cost = recent[0] or 0.0
    recent_in = recent[1] or 0
    recent_out = recent[2] or 0
    recent_runs = recent[3] or 0

    # Per-day breakdown
    daily = db.execute("""
        SELECT DATE(run_time) as day, SUM(estimated_cost_usd), SUM(input_tokens), COUNT(*)
        FROM cron_runs WHERE run_time >= ?
        GROUP BY day ORDER BY day
    """, (cutoff,)).fetchall()

    # Per-agent breakdown (mapped from job_id via registry)
    agent_costs = {}
    reg = load_registry()
    # Simple heuristic: first 8 chars of job_id tend to correlate to agent crons
    all_jobs = db.execute("""
        SELECT job_id, SUM(estimated_cost_usd), SUM(input_tokens), COUNT(*)
        FROM cron_runs WHERE estimated_cost_usd > 0
        GROUP BY job_id ORDER BY SUM(estimated_cost_usd) DESC
    """).fetchall()

    results = {
        "period_days": days,
        "total_cost_usd": round(total, 6),
        "recent_cost_usd": round(recent_cost, 6),
        "recent_input_tokens": recent_in,
        "recent_output_tokens": recent_out,
        "recent_runs": recent_runs,
        "daily": [{"day": r[0], "cost": round(r[1] or 0, 6), "tokens": r[2] or 0, "runs": r[3]} for r in daily],
        "jobs": [{"job_id": j[0][:16], "cost": round(j[1] or 0, 6), "tokens": j[2] or 0, "runs": j[3]} for j in all_jobs],
    }

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(f"📊 Cost Report (last {days} days)")
    print(f"   Period:   {cutoff} — now")
    print(f"   Runs:     {recent_runs}")
    print(f"   Cost:     ${recent_cost:.4f}")
    print(f"   Tokens:   {recent_in:,} in / {recent_out:,} out")
    print(f"   All-time: ${total:.4f}")
    print()

    if daily:
        print(f"{'Date':<14} {'Cost':<10} {'Tokens':<12} {'Runs':<6}")
        print("-" * 44)
        for d in daily:
            print(f"{d[0]:<14} ${d[1] or 0:<7.4f} {d[2] or 0:<12,} {d[3]:<6}")
        print()

    if all_jobs:
        print(f"{'Job ID':<18} {'Cost':<10} {'Tokens':<12} {'Runs':<6}")
        print("-" * 48)
        for j in all_jobs[:10]:
            print(f"{j[0][:16]:<18} ${j[1] or 0:<7.4f} {j[2] or 0:<12,} {j[3]:<6}")
        if len(all_jobs) > 10:
            print(f"   ... and {len(all_jobs) - 10} more jobs")


def cmd_weekly(args):
    """Weekly cost breakdown."""
    db = get_db()
    rows = db.execute("""
        SELECT strftime('%Y-W%W', run_time) as week,
               SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*)
        FROM cron_runs
        WHERE estimated_cost_usd > 0
        GROUP BY week ORDER BY week
    """).fetchall()

    if args.json:
        print(json.dumps([
            {"week": r[0], "cost": round(r[1] or 0, 6), "in_tokens": r[2] or 0,
             "out_tokens": r[3] or 0, "runs": r[4]} for r in rows
        ], indent=2))
        return

    print(f"{'Week':<12} {'Cost':<10} {'In Tokens':<12} {'Out Tokens':<12} {'Runs':<6}")
    print("-" * 55)
    for r in rows:
        print(f"{r[0]:<12} ${r[1] or 0:<7.4f} {r[2] or 0:<12,} {r[3] or 0:<12,} {r[4]:<6}")

    total = sum(r[1] or 0 for r in rows)
    print(f"\nTotal: ${total:.4f}")


def cmd_jobs(args):
    """Per-job cost breakdown."""
    db = get_db()
    rows = db.execute("""
        SELECT job_id, COUNT(*) as runs,
               SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens),
               MIN(run_time) as first_run, MAX(run_time) as last_run,
               SUM(CASE WHEN no_agent=1 THEN 1 ELSE 0 END) as no_agent_count
        FROM cron_runs
        WHERE estimated_cost_usd > 0
        GROUP BY job_id ORDER BY SUM(estimated_cost_usd) DESC
    """).fetchall()

    if args.json:
        print(json.dumps([
            {"job_id": r[0], "runs": r[1], "cost": round(r[2] or 0, 6),
             "in_tokens": r[3] or 0, "out_tokens": r[4] or 0,
             "first_run": r[5], "last_run": r[6]} for r in rows
        ], indent=2))
        return

    print(f"{'Job ID':<20} {'Cost':<10} {'In':<10} {'Out':<10} {'Runs':<6} {'Period':<20}")
    print("-" * 78)
    for r in rows:
        period = f"{r[5][:10] if r[5] else '?'} — {r[6][:10] if r[6] else '?'}"
        print(f"{r[0][:18]:<20} ${r[2] or 0:<7.4f} {r[3] or 0:<10,} {r[4] or 0:<10,} {r[1]:<6} {period:<20}")

    total = sum(r[2] or 0 for r in rows)
    total_runs = sum(r[1] for r in rows)
    print(f"\nTotal: ${total:.4f} across {total_runs} runs")


def main():
    parser = argparse.ArgumentParser(
        description="Fleet cost reporting CLI for Hermes Cortex"
    )
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--weekly", action="store_true", help="Weekly breakdown")
    parser.add_argument("--jobs", action="store_true", help="Per-job breakdown")

    args = parser.parse_args()

    if args.weekly:
        cmd_weekly(args)
    elif args.jobs:
        cmd_jobs(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
