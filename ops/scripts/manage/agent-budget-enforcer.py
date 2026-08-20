#!/usr/bin/env python3
"""
agent-budget-enforcer.py — Per-agent token budget enforcement.

Reads agent registry for budget.daily_token_cap, compares against
today's token usage in cron-costs.db. Alerts when approaching or
exceeding budget. Can block crons from running.

Usage:
    agent-budget-enforcer.py                          # Check all agents
    agent-budget-enforcer.py --agent moses            # Check specific agent
    agent-budget-enforcer.py --block                  # Block over-budget crons (exit 1)
    agent-budget-enforcer.py --threshold 0.8          # Alert at 80% of budget (default)
    agent-budget-enforcer.py --json                   # Machine-readable output

|Exit codes:
|    0 — Under budget
|    1 — At/over budget (when --block)
|    2 — No budget data / agent not found
|
|Watchdog mode (--watchdog):
|    Quiet when under budget (empty stdout — nothing to report)
|    Outputs alert when approaching or exceeding budget
|    Always exits 0 (watchdog pattern — output IS the message)
|    Use as: no_agent cron script for silent budget monitoring
|"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from hermes_tz import format_timestamp
from pathlib import Path

HOME = Path.home()
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"
REGISTRY_PATHS = [
    HOME / ".hermes-cortex" / "state" / "agent-registry.json",
    HOME / "hermes-cortex" / "ops" / "install" / "deploy" / "agent-registry.json.example",
]


def load_registry():
    for p in REGISTRY_PATHS:
        if p.exists():
            return json.loads(p.read_text())
    return {"agents": {}}


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_today_cost(conn: sqlite3.Connection, job_ids: list[str] | None = None) -> float:
    """Sum today's cost for given job IDs (or all if None)."""
    day = today_str()
    if job_ids:
        placeholders = ",".join("?" for _ in job_ids)
        row = conn.execute(
            f"SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM cron_runs "
            f"WHERE run_time LIKE ? AND job_id IN ({placeholders})",
            [f"{day}%"] + job_ids
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM cron_runs WHERE run_time LIKE ?",
            (f"{day}%",)
        ).fetchone()
    return row[0] if row else 0.0


def get_today_tokens(conn: sqlite3.Connection, job_ids: list[str] | None = None) -> int:
    """Sum today's input tokens."""
    day = today_str()
    if job_ids:
        placeholders = ",".join("?" for _ in job_ids)
        row = conn.execute(
            f"SELECT COALESCE(SUM(input_tokens), 0) FROM cron_runs "
            f"WHERE run_time LIKE ? AND job_id IN ({placeholders})",
            [f"{day}%"] + job_ids
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) FROM cron_runs WHERE run_time LIKE ?",
            (f"{day}%",)
        ).fetchone()
    return row[0] if row else 0


def estimate_tokens_from_cost(cost_usd: float, model: str = "deepseek-v4-flash") -> int:
    """Rough token estimate from cost (deepseek flash ~$0.15/M input tokens)."""
    rate = 0.15 / 1_000_000  # $0.15 per million input tokens
    if rate > 0:
        return int(cost_usd / rate)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Per-agent token budget enforcement")
    parser.add_argument("--agent", help="Check specific agent only")
    parser.add_argument("--block", action="store_true",
                        help="Block over-budget crons (exit 1 if over)")
    parser.add_argument("--threshold", type=float, default=0.8,
                        help="Warning threshold as fraction of budget (default: 0.8)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--watchdog", action="store_true",
                        help="Watchdog mode: quiet when under budget, noisy when over (no_agent cron)")
    args = parser.parse_args()

    if not COST_DB.exists():
        print("❌ cron-costs.db not found — deploy cost tracking first")
        sys.exit(2)

    registry = load_registry()
    agents = registry.get("agents", {})
    if not agents:
        print("❌ No agents in registry")
        sys.exit(2)

    conn = sqlite3.connect(str(COST_DB))
    conn.row_factory = sqlite3.Row

    results = []

    for agent_key, agent_data in agents.items():
        if args.agent and agent_key != args.agent:
            continue

        # Get budget from registry
        eco = agent_data.get("fleet_concerns", {}).get("economics", {})
        budget = eco.get("budget", {})
        daily_cap = budget.get("daily_token_cap", 0)
        if isinstance(daily_cap, str):
            try:
                daily_cap = int(daily_cap)
            except (ValueError, TypeError):
                daily_cap = 0

        # Get today's cost/tokens from DB
        # We use all runs since we don't have per-agent mapping in cost DB
        daily_cost = get_today_cost(conn)
        daily_tokens = get_today_tokens(conn)

        # Estimate tokens from cost if direct tokens not available
        if daily_tokens == 0 and daily_cost > 0:
            daily_tokens = estimate_tokens_from_cost(daily_cost)

        # Calculate budget usage
        usage_pct = (daily_tokens / daily_cap * 100) if daily_cap > 0 else 0
        over_budget = daily_cap > 0 and daily_tokens >= daily_cap
        near_budget = daily_cap > 0 and usage_pct >= (args.threshold * 100)

        result = {
            "agent": agent_key,
            "role": agent_data.get("role", "unknown"),
            "daily_token_cap": daily_cap,
            "today_tokens": daily_tokens,
            "today_cost": round(daily_cost, 6),
            "usage_pct": round(usage_pct, 1),
            "over_budget": over_budget,
            "near_budget": near_budget,
        }
        results.append(result)

    conn.close()

    if args.json:
        print(json.dumps(results, indent=2))
        return

    # Watchdog mode: quiet when under budget, noisy when over (no_agent cron pattern)
    if args.watchdog:
        any_alert = False
        for r in results:
            if r["over_budget"] or r["near_budget"]:
                if not any_alert:
                    ts = format_timestamp("%Y-%m-%d %H:%M %Z")
                    print(f"[{ts}] agent-budget-enforcer watchdog:")
                    any_alert = True
                icon = "🔴" if r["over_budget"] else "🟡"
                status = "OVER BUDGET" if r["over_budget"] else f"Near budget (>={args.threshold*100:.0f}%)"
                print(f"  {icon} {r['agent']} ({r['role']}) — {r['today_tokens']:,}/{r['daily_token_cap']:,} tokens ({r['usage_pct']:.1f}%) — {status}")
        if not any_alert:
            return  # silent — nothing to report (watchdog pattern)
        print("")
        print("  Budget enforcer is running in watchdog mode.")
        print("  Use --block for hard enforcement (exit 1 when over budget).")
        return

    any_blocked = False
    for r in results:
        icon = "🔴" if r["over_budget"] else ("🟡" if r["near_budget"] else "🟢")
        print(f"{icon} {r['agent']} ({r['role']})")
        print(f"   Budget:   {r['daily_token_cap']:,} tokens/day")
        print(f"   Today:    {r['today_tokens']:,} tokens (${r['today_cost']:.4f})")
        print(f"   Usage:    {r['usage_pct']:.1f}%")
        if r["over_budget"]:
            print(f"   Status:   🔴 OVER BUDGET")
            any_blocked = True
        elif r["near_budget"]:
            print(f"   Status:   🟡 Near budget (>{args.threshold*100:.0f}%)")
        else:
            print(f"   Status:   🟢 Under budget")
        print()

    if any_blocked and args.block:
        print("🔴 Blocking crons — agents over budget")
        sys.exit(1)
    elif any_blocked:
        print("⚠️  Some agents are over budget (use --block to enforce)")
    else:
        print("✅ All agents within budget")


if __name__ == "__main__":
    main()
