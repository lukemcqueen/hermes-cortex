#!/usr/bin/env python3
"""Tests for axi-telemetry.py — F-022 token/turn baseline harness.

The harness MUST measure token counts from existing cost records out-of-
band — it never runs the task itself (running the task would inflate the
very numbers it measures). This test asserts metering a fixture DB
records the fixture's known counts EXACTLY (no inflation, no rounding
drift, no double-count).

Security constraint (party showstopper): counts-only — the harness never
captures message/task content, only integers.
"""
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "orch_axi_telemetry", _REPO / "ops" / "scripts" / "manage" / "orch-axi-telemetry.py")
MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["axi_telemetry"] = MOD
_SPEC.loader.exec_module(MOD)


def _mkdb():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = sqlite3.connect(tf.name)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE cron_runs (
        id INTEGER PRIMARY KEY, job_id TEXT, run_time TEXT,
        input_tokens INTEGER, output_tokens INTEGER,
        cache_read_tokens INTEGER, cache_write_tokens INTEGER,
        api_calls INTEGER, estimated_cost_usd REAL,
        model TEXT, provider TEXT, no_agent INTEGER, status TEXT)""")
    return conn, tf.name


def _seed(conn, job_id, day, runs):
    """Insert runs for a job on a day; each run is (in, out, cache_r, calls)."""
    for i, (tin, tout, cr, calls) in enumerate(runs):
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, input_tokens, output_tokens, "
            "cache_read_tokens, cache_write_tokens, api_calls, estimated_cost_usd, "
            "model, provider, no_agent, status) VALUES (?,?,?,?,?,0,?,0.001,'m','p',0,'ok')",
            (job_id, f"{day}T0{i}:00:00Z", tin, tout, cr, calls))
    conn.commit()


def test_harness_does_not_inflate_measured():
    """Known fixture counts must be recorded exactly — no inflation."""
    conn, path = _mkdb()
    try:
        _seed(conn, "job-a", "2026-08-24", [(100, 50, 200, 1), (300, 75, 400, 2)])
        _seed(conn, "job-b", "2026-08-24", [(500, 100, 0, 1)])
        _seed(conn, "job-a", "2026-08-23", [(999, 999, 999, 9)])  # prior day — excluded from today

        stats = MOD.meter_job(conn, "job-a", day="2026-08-24")
        assert stats["runs"] == 2, stats
        assert stats["tokens_in"] == 400, stats      # 100+300
        assert stats["tokens_out"] == 125, stats     # 50+75
        assert stats["cache_read"] == 600, stats     # 200+400
        assert stats["api_calls"] == 3, stats        # 1+2

        # job-b: single run
        stats_b = MOD.meter_job(conn, "job-b", day="2026-08-24")
        assert stats_b == {"runs": 1, "tokens_in": 500, "tokens_out": 100,
                           "cache_read": 0, "api_calls": 1}, stats_b
    finally:
        conn.close()
        import os; os.unlink(path)


def test_metric_is_counts_only_never_content():
    """The meter returns ONLY integers — no message/task content."""
    conn, path = _mkdb()
    try:
        _seed(conn, "job-a", "2026-08-24", [(100, 50, 200, 1)])
        stats = MOD.meter_job(conn, "job-a", day="2026-08-24")
        assert all(isinstance(v, int) for v in stats.values()), stats
        # And the baseline builder emits only task-id → counts.
        report = MOD.build_report(conn, day="2026-08-24")
        for entry in report["tasks"]:
            assert set(entry) == {"task_id", "runs", "tokens_in", "tokens_out",
                                  "cache_read", "api_calls"}, entry
    finally:
        conn.close()
        import os; os.unlink(path)
