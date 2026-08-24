#!/usr/bin/env python3
"""Regression tests for max_cost_guard.py daily-budget semantics.

2026-08-24 fleet blocks: agent-fixer-workday ($0.0114 ≥ $0.0092 cap),
cortex-bus-workday ($0.0034 ≥ $0.0025), Gisu's agent-inbox-workday
($0.0116 ≥ $0.0089) — all multi-fire-per-day jobs blocked by comparing
cumulative daily spend against the per-run cap (p95×2.0). Fix: daily
budget = per-run cap × DAILY_MULTIPLIER (default 8) — legitimate cadence
passes, runaway loops still trip.
"""
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "max_cost_guard", _REPO / "ops" / "scripts" / "manage" / "max_cost_guard.py")
MG = importlib.util.module_from_spec(_SPEC)
sys.modules["max_cost_guard"] = MG
_SPEC.loader.exec_module(MG)


def _mkdb():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tf.name)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE cron_runs (
        id INTEGER PRIMARY KEY, job_id TEXT, run_time TEXT,
        estimated_cost_usd REAL, no_agent INTEGER)""")
    return conn, tf.name


def _seed_history(conn, job_id, n=10, cost=0.10):
    for i in range(n):
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES (?, ?, ?, 0)",
            (job_id, f"2026-08-{10+i:02d}T00:00:00Z", cost))
    conn.commit()


def _today_run(conn, job_id, cost, minute):
    day = MG._today_utc_prefix()
    conn.execute(
        "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
        "VALUES (?, ?, ?, 0)", (job_id, f"{day}T03:{minute:02d}:00Z", cost))
    conn.commit()


def test_multi_fire_per_day_allowed():
    """Cadence: daily spend > per-run cap but < daily budget → allow."""
    conn, path = _mkdb()
    try:
        _seed_history(conn, "workday", n=10, cost=0.10)  # p95=0.10, cap=0.20
        _today_run(conn, "workday", 0.10, 1)  # today: 0.10
        _today_run(conn, "workday", 0.10, 2)  # today: 0.20 ≥ cap, < budget 1.60
        d = MG.should_fire("workday", conn=conn)
        assert d["decision"] == "allow", d
    finally:
        conn.close()
        import os; os.unlink(path)


def test_runaway_loop_blocked():
    """A loop firing well past the daily budget still blocks."""
    conn, path = _mkdb()
    try:
        _seed_history(conn, "loop", n=10, cost=0.10)  # cap=0.20, budget=1.60
        for i in range(20):
            _today_run(conn, "loop", 0.10, i)  # today: 2.00 ≥ 1.60
        d = MG.should_fire("loop", conn=conn)
        assert d["decision"] == "block", d
    finally:
        conn.close()
        import os; os.unlink(path)


def test_daily_budget_reflects_multiplier():
    conn, path = _mkdb()
    try:
        _seed_history(conn, "job", n=10, cost=0.10)
        cap = MG.compute_cap("job", conn)
        assert cap == 0.20
        assert abs(cap * MG.DAILY_MULTIPLIER - 1.60) < 1e-9
    finally:
        conn.close()
        import os; os.unlink(path)
