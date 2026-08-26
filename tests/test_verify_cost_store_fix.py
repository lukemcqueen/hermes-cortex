#!/usr/bin/env python3
"""Tests for verify-cost-store-fix — O1-S3 fleet propagation probe (9befa548).

Run: python3 -m pytest tests/test_verify_cost_store_fix.py -v
     (or: python3 tests/test_verify_cost_store_fix.py)
"""
import importlib.util
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_MANAGE = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage"
_spec = importlib.util.spec_from_file_location("verify_cost_store_fix", _MANAGE / "verify-cost-store-fix.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

MARKERS_OK = (
    "# O1-S3 fix\n"
    "PRICE_HIT = 0.007\n"
    "def record_run(job_id, cost_data):\n"
    "    # The provider number is intentionally ignored.\n"
    "    est = _compute_cost(in_tok, out_tok, cr_tok, cw_tok, run_dt)\n"
    "    if r['rate_version'] == RATE_VERSION and abs(float(r['estimated_cost_usd']) - new_cost) < 1e-4:\n"
    "        pass\n"
)


def test_is_peak_boundaries():
    assert _mod.is_peak(datetime(2026, 8, 21, 1, 0)) is True
    assert _mod.is_peak(datetime(2026, 8, 21, 3, 59)) is True
    assert _mod.is_peak(datetime(2026, 8, 21, 4, 0)) is False
    assert _mod.is_peak(datetime(2026, 8, 21, 6, 0)) is True
    assert _mod.is_peak(datetime(2026, 8, 21, 9, 59)) is True
    assert _mod.is_peak(datetime(2026, 8, 21, 10, 0)) is False
    assert _mod.is_peak(datetime(2026, 8, 21, 0, 59)) is False


def test_compute_cost_matches_local_schedule():
    # 1M miss + 1M output, off-peak = $0.22 + $0.66
    dt = datetime(2026, 8, 21, 12, 0)
    cost = _mod.compute_cost(1_000_000, 1_000_000, 0, 0, dt)
    assert abs(cost - 0.88) < 1e-9
    # peak doubles
    cost_peak = _mod.compute_cost(1_000_000, 1_000_000, 0, 0, datetime(2026, 8, 21, 2, 0))
    assert abs(cost_peak - 1.76) < 1e-9


def test_check_deployed_detects_markers():
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "cost_store.py"
        fake.write_text(MARKERS_OK)
        _mod.DEPLOYED = fake
        ok, detail = _mod.check_deployed()
        assert ok is True, detail
        # stale file missing the consistency guard
        fake.write_text("# O1-S3 fix\nPRICE_HIT = 0.007\ndef record_run():\n    pass\n")
        ok, detail = _mod.check_deployed()
        assert ok is False
        assert "STALE" in detail


def test_check_row_catches_stale_provider_estimate():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "cron-costs.db"
        con = sqlite3.connect(str(db))
        con.execute(
            """CREATE TABLE cron_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, run_time TEXT,
                input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
                cache_write_tokens INTEGER, estimated_cost_usd REAL, model TEXT,
                provider TEXT, no_agent INTEGER, status TEXT, rate_version TEXT)"""
        )
        # stale provider estimate: 10K miss + 5K out at 02:00 UTC (peak) —
        # old-table estimate would be (0.14*10K + 0.28*5K)/1M = $0.0028;
        # local schedule = (0.22*10K + 0.66*5K)*2/1M = $0.011
        con.execute(
            """INSERT INTO cron_runs (job_id, run_time, input_tokens, output_tokens,
               cache_read_tokens, cache_write_tokens, estimated_cost_usd, no_agent,
               status, rate_version) VALUES ('job1', '2026-08-26T02:00:00Z',
               10000, 5000, 0, 0, 0.0028, 0, 'ok', '2026-08-16')"""
        )
        con.commit()
        con.close()
        _mod.COST_DB = db
        ok, detail = _mod.check_row()
        assert ok is False, detail  # stale estimate must be flagged
        assert "MISMATCH" in detail


def test_check_row_pass_on_consistent_row():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "cron-costs.db"
        con = sqlite3.connect(str(db))
        con.execute(
            """CREATE TABLE cron_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, run_time TEXT,
                input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
                cache_write_tokens INTEGER, estimated_cost_usd REAL, model TEXT,
                provider TEXT, no_agent INTEGER, status TEXT, rate_version TEXT)"""
        )
        # off-peak row priced at local schedule: (0.22*10K + 0.66*5K)/1M = $0.0055
        con.execute(
            """INSERT INTO cron_runs (job_id, run_time, input_tokens, output_tokens,
               cache_read_tokens, cache_write_tokens, estimated_cost_usd, no_agent,
               status, rate_version) VALUES ('job1', '2026-08-26T12:00:00Z',
               10000, 5000, 0, 0, 0.0055, 0, 'ok', '2026-08-16')"""
        )
        con.commit()
        con.close()
        _mod.COST_DB = db
        ok, detail = _mod.check_row()
        assert ok is True, detail
        assert "MATCH" in detail


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
