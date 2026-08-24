#!/usr/bin/env python3
"""axi-telemetry.py — F-022 token/turn baseline harness.

Measures tokens+turns per recurring task (doctor, bus inspection, task
list, cron) from EXISTING cost records — out-of-band, never by running
the task itself (running the task would inflate the very numbers it
measures).

Security invariant (party showstopper): COUNTS ONLY. The harness reads
integers from cron-costs.db (input/output/cache tokens, api_calls per
job_id) and never captures message/task content.

Source of truth: ~/.hermes/cron/cron-costs.db (cron_runs table — the
same DB the cost tracker writes; counts-only by construction).

CLI:
    axi-telemetry.py --baseline [--day YYYY-MM-DD]  # write state/axi-baseline.json
    axi-telemetry.py --report [--day YYYY-MM-DD]     # print today's counts
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HOME = Path.home()
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"
BASELINE_PATH = HOME / ".hermes-cortex" / "state" / "axi-baseline.json"

_METRIC_KEYS = ("runs", "tokens_in", "tokens_out", "cache_read", "api_calls")


def meter_job(conn: sqlite3.Connection, job_id: str,
              day: Optional[str] = None) -> dict:
    """Count-only metrics for one job on one UTC day (default: today).

    Returns ONLY integers — never content. A day with no runs returns
    all-zero counts (not None), so a baseline is complete.
    """
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        """SELECT COUNT(*) AS runs,
                  COALESCE(SUM(input_tokens),0) AS tin,
                  COALESCE(SUM(output_tokens),0) AS tout,
                  COALESCE(SUM(cache_read_tokens),0) AS cr,
                  COALESCE(SUM(api_calls),0) AS calls
           FROM cron_runs
           WHERE job_id = ? AND run_time LIKE ? AND (no_agent IS NULL OR no_agent = 0)""",
        (job_id, f"{day}%"),
    ).fetchone()
    return {
        "runs": int(row["runs"]),
        "tokens_in": int(row["tin"]),
        "tokens_out": int(row["tout"]),
        "cache_read": int(row["cr"]),
        "api_calls": int(row["calls"]),
    }


def build_report(conn: sqlite3.Connection,
                 day: Optional[str] = None) -> dict:
    """Counts for every LLM-driven job with activity that day."""
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    job_ids = [r["job_id"] for r in conn.execute(
        "SELECT DISTINCT job_id FROM cron_runs WHERE run_time LIKE ? "
        "AND (no_agent IS NULL OR no_agent = 0)",
        (f"{day}%",))]
    tasks = []
    for jid in sorted(job_ids):
        tasks.append({"task_id": jid, **meter_job(conn, jid, day)})
    return {"day": day, "generated_at": datetime.now(timezone.utc).isoformat(),
            "tasks": tasks}


def write_baseline(conn: sqlite3.Connection,
                   day: Optional[str] = None) -> Path:
    """Persist the baseline report; 0600 perms (counts are sensitive-ish)."""
    report = build_report(conn, day)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(report, indent=2) + "\n")
    BASELINE_PATH.chmod(0o600)
    return BASELINE_PATH


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="F-022 token/turn baseline harness")
    ap.add_argument("--baseline", action="store_true",
                    help="write state/axi-baseline.json")
    ap.add_argument("--report", action="store_true",
                    help="print today's counts as JSON")
    ap.add_argument("--day", default=None, help="UTC day YYYY-MM-DD (default today)")
    args = ap.parse_args(argv)

    if not COST_DB.exists():
        print(f"error: {COST_DB} missing — no cost records to meter", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(COST_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Default action (no flags, e.g. from the daily cron) = baseline.
        # The cron convention on this fleet is scripts that default to the
        # right unattended behavior; --report is the explicit human mode.
        if args.baseline or (not args.report):
            path = write_baseline(conn, args.day)
            print(f"baseline written: {path}")
            return 0
        report = build_report(conn, args.day)
        print(json.dumps(report, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
