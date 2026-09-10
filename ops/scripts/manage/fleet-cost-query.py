#!/usr/bin/env python3
"""Quick cost DB query for fleet dispatch — outputs JSON summary."""
import json, sqlite3, sys
from pathlib import Path

db_path = Path.home() / ".hermes" / "cron" / "cron-costs.db"
if not db_path.exists():
    print(json.dumps({"error": "NO_COST_DB", "host": __import__("socket").gethostname()}))
    sys.exit(0)

db = sqlite3.connect(str(db_path))
db.row_factory = sqlite3.Row

total = db.execute("SELECT SUM(estimated_cost_usd) FROM cron_runs").fetchone()[0] or 0.0

# Last 30 days
cutoff_30 = (__import__("datetime").datetime.now() - __import__("datetime").timedelta(days=30)).isoformat()
recent = db.execute(
    "SELECT SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) "
    "FROM cron_runs WHERE run_time >= ?", (cutoff_30,)
).fetchone()

# Per-model breakdown
models = db.execute(
    "SELECT COALESCE(model, 'unknown') as model, SUM(estimated_cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) "
    "FROM cron_runs WHERE estimated_cost_usd > 0 GROUP BY model ORDER BY SUM(estimated_cost_usd) DESC"
).fetchall()

# Top 5 jobs
jobs = db.execute(
    "SELECT job_id, SUM(estimated_cost_usd), COUNT(*) "
    "FROM cron_runs WHERE estimated_cost_usd > 0 "
    "GROUP BY job_id ORDER BY SUM(estimated_cost_usd) DESC LIMIT 5"
).fetchall()

# Daily costs
daily = db.execute(
    "SELECT DATE(run_time) as day, SUM(estimated_cost_usd) "
    "FROM cron_runs WHERE run_time >= ? "
    "GROUP BY day ORDER BY day", (cutoff_30,)
).fetchall()

result = {
    "host": __import__("socket").gethostname(),
    "total_cost_usd": round(total, 6),
    "recent_30d_usd": round(recent[0] or 0, 6),
    "recent_30d_input_tokens": recent[1] or 0,
    "recent_30d_output_tokens": recent[2] or 0,
    "recent_30d_runs": recent[3] or 0,
    "by_model": [{"model": m[0], "cost": round(m[1] or 0, 6), "in_tok": m[2] or 0, "out_tok": m[3] or 0, "runs": m[4]} for m in models],
    "top_5_jobs": [{"job_id": j[0][:20], "cost": round(j[1] or 0, 6), "runs": j[2]} for j in jobs],
    "daily_30d": [{"day": d[0], "cost": round(d[1] or 0, 6)} for d in daily],
}
print(json.dumps(result, indent=2))