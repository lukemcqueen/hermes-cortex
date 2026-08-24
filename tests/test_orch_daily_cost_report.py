#!/usr/bin/env python3
"""Tests for orch-daily-cost-report — cost math + report aggregation (O1-S2).

Run: python3 -m pytest tests/test_orch_daily_cost_report.py -v
     (or: python3 tests/test_orch_daily_cost_report.py)
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_MANAGE = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage"
_spec = importlib.util.spec_from_file_location("orch_daily_cost_report", _MANAGE / "orch-daily-cost-report.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PRICE_HIT = _mod.PRICE_HIT
PRICE_MISS = _mod.PRICE_MISS
PRICE_OUT = _mod.PRICE_OUT
PEAK_MULT = _mod.PEAK_MULT
build_report = _mod.build_report
compute_cost = _mod.compute_cost
is_peak_hour = _mod.is_peak_hour
render_text = _mod.render_text


def test_peak_hour_boundaries():
    # 01:00-04:00 and 06:00-10:00 UTC are peak
    assert is_peak_hour(datetime(2026, 8, 21, 1, 0)) is True
    assert is_peak_hour(datetime(2026, 8, 21, 3, 59)) is True
    assert is_peak_hour(datetime(2026, 8, 21, 4, 0)) is False
    assert is_peak_hour(datetime(2026, 8, 21, 6, 0)) is True
    assert is_peak_hour(datetime(2026, 8, 21, 9, 59)) is True
    assert is_peak_hour(datetime(2026, 8, 21, 10, 0)) is False
    assert is_peak_hour(datetime(2026, 8, 21, 0, 59)) is False
    assert is_peak_hour(datetime(2026, 8, 21, 5, 0)) is False


def test_compute_cost_offpeak_all_miss():
    # 1M prompt (all miss) + 1M output, off-peak
    dt = datetime(2026, 8, 21, 12, 0)  # 12:00 UTC = off-peak
    cost = compute_cost(1_000_000, 1_000_000, 0, 0, dt)
    expected = (PRICE_MISS + PRICE_OUT)  # $0.22 + $0.66
    assert abs(cost - expected) < 1e-9, f"expected {expected}, got {cost}"


def test_compute_cost_cache_hit_31x_cheaper():
    # 1M prompt, 900K cache-hit vs all miss — hit should be ~31x cheaper on input
    dt = datetime(2026, 8, 21, 12, 0)
    all_miss = compute_cost(1_000_000, 0, 0, 0, dt)
    partial_hit = compute_cost(1_000_000, 0, 900_000, 0, dt)
    # all-miss input = $0.22; 90% hit = 0.9*0.007 + 0.1*0.22 = $0.0283
    expected_partial = (900_000 * PRICE_HIT + 100_000 * PRICE_MISS) / 1e6
    assert abs(partial_hit - expected_partial) < 1e-9
    assert all_miss > partial_hit * 7  # roughly 7.8x at 90% hit


def test_compute_cost_peak_doubles():
    dt_peak = datetime(2026, 8, 21, 2, 0)
    dt_off = datetime(2026, 8, 21, 12, 0)
    cost_peak = compute_cost(1_000_000, 1_000_000, 0, 0, dt_peak)
    cost_off = compute_cost(1_000_000, 1_000_000, 0, 0, dt_off)
    assert abs(cost_peak - cost_off * PEAK_MULT) < 1e-9


def test_build_report_aggregation_and_coverage():
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "usage_audit.jsonl"
        # 2 runs TODAY (relative timestamps — the test must not rot as
        # wall-clock advances): one off-peak all-miss cron, one peak
        # cache-hit. Peak = 01-04 UTC, off-peak = 12 UTC.
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        rows = [
            {"ts": now.replace(hour=12).isoformat() + "Z", "job_id": "abc123", "fire_id": "f1",
             "prompt_tokens": 1_000_000, "completion_tokens": 0,
             "cache_read_tokens": 0, "cache_write_tokens": 0},
            {"ts": now.replace(hour=2).isoformat() + "Z", "job_id": "def456", "fire_id": "f2",
             "prompt_tokens": 1_000_000, "completion_tokens": 0,
             "cache_read_tokens": 900_000, "cache_write_tokens": 0},
        ]
        audit.write_text("\n".join(json.dumps(r) for r in rows))

        # cost_db path that does not exist → coverage MISSING, not zero
        missing_db = Path(td) / "nope.db"
        r = build_report(days=1, audit_path=audit, cost_db=missing_db)

        assert r["summary"]["runs"] == 2
        # first run: off-peak, 1M miss = $0.22 ; second: peak, 10% miss = $0.044
        expected_cost = 0.22 + (900_000 * PRICE_HIT + 100_000 * PRICE_MISS) / 1e6 * PEAK_MULT
        assert abs(r["summary"]["cost_usd"] - round(expected_cost, 2)) < 0.011
        assert r["summary"]["peak_runs"] == 1
        assert r["summary"]["cache_hit_pct"] == 45.0  # 900K/2M
        assert r["by_category"]["cron"]["runs"] == 2
        assert r["coverage"]["usage_audit"] == "ok"
        assert r["coverage"]["cron_costs_db"] == "MISSING"

        text = render_text(r)
        assert "GAPS" in text  # QA showstopper: gaps shown, never zeros


def test_build_report_missing_audit_shows_gap():
    with tempfile.TemporaryDirectory() as td:
        r = build_report(days=1, audit_path=Path(td) / "no-audit.jsonl",
                         cost_db=Path(td) / "no-db.db")
        assert r["coverage"]["usage_audit"] == "MISSING"
        assert r["summary"]["runs"] == 0
        assert "GAPS" in render_text(r)


def test_build_report_ignores_old_rows():
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "usage_audit.jsonl"
        rows = [
            {"ts": "2026-08-01T12:00:00.000Z", "job_id": "old1",
             "prompt_tokens": 10_000_000, "completion_tokens": 0,
             "cache_read_tokens": 0, "cache_write_tokens": 0},
        ]
        audit.write_text("\n".join(json.dumps(r) for r in rows))
        r = build_report(days=1, audit_path=audit, cost_db=Path(td) / "no.db")
        assert r["summary"]["runs"] == 0


def test_render_text_avoids_secret_redaction():
    """The redactor masks 'Tokens: <value>' as a secret field (TOKEN pattern).
    The report must NOT use the 'Tokens:' label or its numbers get ***'d."""
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "usage_audit.jsonl"
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        audit.write_text("\n".join([
            json.dumps({"ts": now.replace(hour=12).isoformat() + "Z", "job_id": "abc123",
                        "prompt_tokens": 85_000_000, "completion_tokens": 600_000,
                        "cache_read_tokens": 0, "cache_write_tokens": 0}),
        ]))
        r = build_report(days=1, audit_path=audit, cost_db=Path(td) / "no.db")
        text = render_text(r)
        assert "Tokens:" not in text, "label 'Tokens:' triggers redactor masking"
        assert "Tokens →" in text
        # 85M must survive as a literal, not ***
        assert "85M" in text and "***" not in text


def test_sessions_table_source():
    """Interactive sessions (telegram/cli/subagent) come from state.db sessions
    table — Hermes persists per-session tokens+cost live. Report must include
    them and show coverage."""
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "cron" / "usage_audit.jsonl"
        audit.parent.mkdir(parents=True)
        audit.write_text("")  # empty audit
        # fake state.db with one telegram session
        sdb = Path(td) / "cron" / ".." / "state.db"  # -> td/state.db
        sdb = sdb.resolve()
        con = sqlite3.connect(str(sdb))
        con.execute("""CREATE TABLE sessions (
            id TEXT, source TEXT, started_at REAL, ended_at REAL, end_reason TEXT,
            estimated_cost_usd REAL, input_tokens INTEGER, output_tokens INTEGER,
            cache_read_tokens INTEGER, cache_write_tokens INTEGER)""")
        import time
        now = time.time()
        con.execute("""INSERT INTO sessions
            (id, source, started_at, estimated_cost_usd, input_tokens, output_tokens, cache_read_tokens)
            VALUES ('s1','telegram',?, 1.25, 5000000, 100000, 4000000)""", (now - 3600,))
        # an OLD session (9 days ago) must be excluded — guards the timezone bug
        # where naive-UTC .timestamp() misread the cutoff as local (+8.6h shift)
        con.execute("""INSERT INTO sessions
            (id, source, started_at, estimated_cost_usd, input_tokens, output_tokens, cache_read_tokens)
            VALUES ('s0','telegram',?, 9.99, 90000000, 100000, 0)""", (now - 9*86400,))
        con.commit(); con.close()

        r = build_report(days=1, audit_path=audit, cost_db=Path(td) / "nope.db")
        assert r["coverage"]["sessions_db"] == "ok"
        assert r["by_category"]["session"]["runs"] == 1, "old session leaked in (timezone bug)"
        assert abs(r["by_category"]["session"]["cost_usd"] - 1.25) < 0.01
        assert r["by_category"]["session"]["prompt_m"] == 5.0


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
