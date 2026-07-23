#!/usr/bin/env python3
"""
cron-cost-report.py — Weekly cron cost report.

Queries ~/.hermes/cron/cron-costs.db for costs in the past 7 days
and outputs a deliverable summary. Silent on success if costs are low.
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.expanduser("~/.hermes/cron/cron-costs.db")

COST_WARNING_THRESHOLD = 0.50  # $0.50/week triggers detailed report
SILENT_THRESHOLD = 0.05        # $0.05/week stays silent

def get_job_name_map():
    """Try to map job IDs to names from the cron jobs.json."""
    jobs_path = os.path.expanduser("~/.hermes/cron/jobs.json")
    if not os.path.exists(jobs_path):
        return {}
    try:
        import json
        with open(jobs_path) as f:
            jobs = json.load(f)
        # jobs.json can be list or dict
        if isinstance(jobs, list):
            return {j.get("id", ""): j.get("name", "") for j in jobs if j.get("id")}
        elif isinstance(jobs, dict):
            return {jid: j.get("name", "") for jid, j in jobs.items()}
    except Exception:
        pass
    return {}

def main():
    if not os.path.exists(DB_PATH):
        # Cost tracking not deployed yet — silent
        return

    db = sqlite3.connect(DB_PATH)
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    
    # Get aggregate for the week
    c = db.execute("""
        SELECT 
            COUNT(*) as total_runs,
            SUM(estimated_cost_usd) as total_cost,
            SUM(input_tokens + output_tokens) as total_tokens,
            SUM(api_calls) as total_api_calls
        FROM cron_runs 
        WHERE run_time >= ?
    """, (week_ago,))
    agg = c.fetchone()
    total_runs, total_cost, total_tokens, total_api_calls = agg
    
    total_cost = total_cost or 0.0
    total_tokens = total_tokens or 0
    total_api_calls = total_api_calls or 0

    # Silent if below threshold
    if total_cost < SILENT_THRESHOLD and total_runs > 0:
        return

    # Get top jobs by cost
    name_map = get_job_name_map()
    c = db.execute("""
        SELECT job_id, 
               COUNT(*) as runs,
               SUM(estimated_cost_usd) as cost,
               SUM(input_tokens + output_tokens) as tokens,
               COUNT(CASE WHEN status != 'ok' THEN 1 END) as failures
        FROM cron_runs 
        WHERE run_time >= ?
        GROUP BY job_id
        ORDER BY cost DESC
        LIMIT 20
    """, (week_ago,))
    top_jobs = c.fetchall()
    db.close()

    # Format output
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    
    if total_cost < COST_WARNING_THRESHOLD:
        lines.append(f"📊 **Weekly Cron Costs ({now})**")
        lines.append(f"Total: ${total_cost:.4f} | {total_runs} runs | {total_tokens:,} tokens")
        if top_jobs:
            lines.append("\nTop jobs:")
            for jid, runs, cost, tokens, failures in top_jobs[:5]:
                if cost and cost > 0.001:
                    name = name_map.get(jid, jid[:12])
                    lines.append(f"  • {name}: ${cost:.4f} ({runs} runs, {tokens:,} tokens{f', {failures} failures' if failures else ''})")
        lines.append("\n✅ Under $0.50/week — nominal")
    else:
        lines.append(f"⚠️ **Weekly Cron Costs — ${total_cost:.2f}** ({now})")
        lines.append(f"Total: ${total_cost:.4f} | {total_runs} runs | {total_tokens:,} tokens | {total_api_calls} API calls")
        lines.append("\nBreakdown:")
        for jid, runs, cost, tokens, failures in top_jobs:
            if cost and cost > 0.001:
                name = name_map.get(jid, jid[:12])
                lines.append(f"  • {name}: ${cost:.4f} ({runs} runs, {tokens:,} tokens{f', ⚠️ {failures} failures' if failures else ' ✓'}))")
    
    sys.stdout.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
