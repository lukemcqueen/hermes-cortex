#!/usr/bin/env python3
"""
max_cost_guard.py — O6-S1 per-job MAX_COST pre-fire guard.

Answers "should this cron job fire right now?" at request time, based on
the job's historical cost distribution in cron-costs.db.

Rule (per HC gaps party 2026-08-21, O6 dissection):
  - cap = p95(historical per-run cost) × headroom, computed over a lookback
    window of runs with estimated_cost_usd > 0.
  - A fire is BLOCKED when the job's accumulated cost TODAY already meets or
    exceeds the cap (the job is re-firing after it already spent more than a
    typical run today).
  - Overnight orchestrator jobs (name prefix from MAX_COST_EXEMPT_PREFIX,
    default "orch-") are exempt — the orchestrator's autonomous work must
    never be killed by its own cost guard.
  - FAILS OPEN: missing DB, missing data, insufficient history (<3 runs),
    or any exception → ALLOW. The guard can only block on an affirmative
    over-cap verdict with real history.

Deployed to ~/.hermes/hermes-agent/cron/max_cost_guard.py by the installer
(install-cron-cost-tracking.py, O6-S1 section) and re-applied by the same
O1-S3 post-update hook that protects cost_store.py.

CLI:
    max_cost_guard.py --caps [--json]              # print computed caps
    max_cost_guard.py --check <job-id> [--job-name N] [--json]
    max_cost_guard.py --test-self                  # hermetic unit checks
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
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_HEADROOM = 2.0
MIN_SAMPLES = 3
EXEMPT_PREFIX = os.environ.get("MAX_COST_EXEMPT_PREFIX", "orch-").split(",")


def _today_utc_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _p95(sorted_costs: list[float]) -> float:
    """Nearest-rank p95 on a sorted ascending list (len >= 1)."""
    if not sorted_costs:
        return 0.0
    idx = max(0, min(len(sorted_costs) - 1, int(0.95 * len(sorted_costs))))
    return sorted_costs[idx]


def compute_cap(job_id: str, conn: sqlite3.Connection,
                lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                headroom: float = DEFAULT_HEADROOM) -> Optional[float]:
    """Return the per-run cost cap for a job, or None when history is
    insufficient to set one (fail open — no cap = no block)."""
    cutoff = (datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - __import__("datetime").timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        """SELECT estimated_cost_usd FROM cron_runs
           WHERE job_id = ? AND run_time >= ? AND estimated_cost_usd > 0
             AND (no_agent IS NULL OR no_agent = 0)
           ORDER BY run_time""",
        (job_id, cutoff),
    ).fetchall()
    costs = sorted(r["estimated_cost_usd"] for r in rows)
    if len(costs) < MIN_SAMPLES:
        return None
    return _p95(costs) * headroom


def today_spend(job_id: str, conn: sqlite3.Connection) -> float:
    day = _today_utc_prefix()
    row = conn.execute(
        """SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM cron_runs
           WHERE job_id = ? AND run_time LIKE ?""",
        (job_id, f"{day}%"),
    ).fetchone()
    return float(row[0]) if row else 0.0


def should_fire(job_id: str, job_name: Optional[str] = None,
                conn: Optional[sqlite3.Connection] = None) -> dict:
    """Decision for a single fire. Returns {'decision': 'allow'|'block',
    'reason': str, 'cap': float|None, 'today_spend': float}.

    Fails open: ANY problem (missing DB, no history, exception) → allow.
    """
    result = {"decision": "allow", "reason": "", "cap": None,
              "today_spend": 0.0, "job_name": job_name}
    try:
        # Exempt orchestrator jobs (overnight autonomous work).
        if job_name:
            for prefix in EXEMPT_PREFIX:
                if prefix and job_name.startswith(prefix.strip()):
                    result["reason"] = f"exempt (prefix '{prefix}')"
                    return result
        if not COST_DB.exists():
            result["reason"] = "cron-costs.db missing — fail open"
            return result
        if conn is None:
            conn = sqlite3.connect(str(COST_DB))
            conn.row_factory = sqlite3.Row
            close_conn = True
        else:
            close_conn = False
        try:
            cap = compute_cap(job_id, conn)
            spend = today_spend(job_id, conn)
            result["cap"] = cap
            result["today_spend"] = round(spend, 6)
            if cap is None:
                result["reason"] = "insufficient history — fail open"
                return result
            if spend >= cap:
                result["decision"] = "block"
                result["reason"] = (
                    f"today spend ${spend:.4f} >= cap ${cap:.4f} "
                    f"(p95×{DEFAULT_HEADROOM})"
                )
            else:
                result["reason"] = (
                    f"today spend ${spend:.4f} < cap ${cap:.4f}"
                )
            return result
        finally:
            if close_conn:
                conn.close()
    except Exception as exc:  # fail open, never crash the scheduler
        result["reason"] = f"guard error ({type(exc).__name__}) — fail open"
        return result


def caps_table(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """SELECT DISTINCT job_id FROM cron_runs
           WHERE estimated_cost_usd > 0 AND (no_agent IS NULL OR no_agent = 0)"""
    ).fetchall()
    out = {}
    for r in rows:
        cap = compute_cap(r["job_id"], conn)
        if cap is not None:
            out[r["job_id"]] = {"cap_usd": round(cap, 6),
                                "headroom": DEFAULT_HEADROOM}
    return out


def _test_self() -> int:
    import tempfile
    fails = []
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE cron_runs (
        id INTEGER PRIMARY KEY, job_id TEXT, run_time TEXT,
        estimated_cost_usd REAL, no_agent INTEGER)""")
    # 10 runs at $0.10 → p95 = 0.10, cap = 0.20 with headroom 2.0
    for i in range(10):
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES (?, ?, ?, 0)",
            ("testjob", f"2026-08-{10+i:02d}T00:00:00Z", 0.10),
        )
    # today: 2 runs at $0.10 each → spend 0.20 >= cap 0.20 → BLOCK
    day = _today_utc_prefix()
    conn.execute(
        "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
        "VALUES ('testjob', ?, 0.10, 0)", (f"{day}T01:00:00Z",))
    conn.execute(
        "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
        "VALUES ('testjob', ?, 0.10, 0)", (f"{day}T02:00:00Z",))
    # insufficient-history job → allow
    conn.execute(
        "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
        "VALUES ('newjob', '2026-08-20T00:00:00Z', 0.05, 0)")
    # exempt orch job → allow even with spend
    conn.execute(
        "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
        "VALUES ('orch-test', ?, 0.50, 0)", (f"{day}T01:00:00Z",))
    conn.commit()

    d = should_fire("testjob", conn=conn)
    if d["decision"] != "block":
        fails.append(f"testjob should BLOCK, got {d}")
    d2 = should_fire("newjob", conn=conn)
    if d2["decision"] != "allow":
        fails.append(f"newjob should ALLOW (insufficient), got {d2}")
    d3 = should_fire("orch-test", "orch-test", conn=conn)
    if d3["decision"] != "allow":
        fails.append(f"orch-test should ALLOW (exempt), got {d3}")
    d4 = should_fire("nonexistent", conn=conn)
    if d4["decision"] != "allow":
        fails.append(f"nonexistent should ALLOW (no data), got {d4}")
    conn.close()
    os.unlink(db_path)
    if fails:
        print("SELF-TEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELF-TEST OK: block/allow/exempt/no-data verdicts verified")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="O6-S1 per-job MAX_COST guard")
    ap.add_argument("--caps", action="store_true", help="print computed caps")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--check", metavar="JOB_ID", help="decide one fire")
    ap.add_argument("--job-name", metavar="NAME", help="job name (for exemption)")
    ap.add_argument("--test-self", action="store_true", help="run hermetic checks")
    args = ap.parse_args(argv)

    if args.test_self:
        return _test_self()

    if args.check:
        d = should_fire(args.check, job_name=args.job_name)
        if args.json:
            print(json.dumps(d, indent=2))
        else:
            print(f"{d['decision'].upper()}: {d['reason']}")
        return 0 if d["decision"] == "allow" else 1

    if args.caps:
        if not COST_DB.exists():
            print("cron-costs.db missing", file=sys.stderr)
            return 2
        conn = sqlite3.connect(str(COST_DB))
        conn.row_factory = sqlite3.Row
        table = caps_table(conn)
        conn.close()
        if args.json:
            print(json.dumps(table, indent=2))
        else:
            for jid, info in sorted(table.items(), key=lambda kv: -kv[1]["cap_usd"]):
                print(f"{jid[:14]:16} cap=${info['cap_usd']:.4f} "
                      f"(headroom {info['headroom']}x)")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
