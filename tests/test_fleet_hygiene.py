#!/usr/bin/env python3
"""Tests for fleet-hygiene — unified fleet hygiene CLI (merged 2026-08-27).

Covers both subcommands:
  - cost-store: O1-S3 fleet propagation probe (ported from
    test_verify_cost_store_fix.py) — is_peak boundaries, local-rate
    compute, deployed-marker detection, row spot-check.
  - langfuse: auth resolution, traces/keys check, exit-code conventions.
  - shared reporting: PASS/FAIL/UNVERIFIABLE + exit codes 0/1/2.

Run: python3 -m pytest tests/test_fleet_hygiene.py -v
     (or: python3 tests/test_fleet_hygiene.py)
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_MANAGE = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage"
_spec = importlib.util.spec_from_file_location("fleet_hygiene", _MANAGE / "fleet-hygiene.py")
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


class _Args:
    def __init__(self, json_out=False):
        self.json = json_out


# ────────────────────────────────────────────────────────────────
# cost-store subcommand
# ────────────────────────────────────────────────────────────────
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


def test_check_deployed_cost_store_detects_markers():
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "cost_store.py"
        fake.write_text(MARKERS_OK)
        _mod.DEPLOYED_COST_STORE = fake
        ok, detail = _mod.check_deployed_cost_store()
        assert ok is True, detail
        # stale file missing the consistency guard
        fake.write_text("# O1-S3 fix\nPRICE_HIT = 0.007\ndef record_run():\n    pass\n")
        ok, detail = _mod.check_deployed_cost_store()
        assert ok is False
        assert "STALE" in detail


def test_check_cost_row_catches_stale_provider_estimate():
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
        ok, detail = _mod.check_cost_row()
        assert ok is False, detail  # stale estimate must be flagged
        assert "MISMATCH" in detail


def test_check_cost_row_pass_on_consistent_row():
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
        ok, detail = _mod.check_cost_row()
        assert ok is True, detail
        assert "MATCH" in detail


def test_cost_store_exit_codes():
    """cmd_cost_store returns 0/1/2 consistently with overall."""
    # missing DB → UNVERIFIABLE → 2
    with tempfile.TemporaryDirectory() as td:
        _mod.DEPLOYED_COST_STORE = Path(td) / "missing.py"
        _mod.COST_DB = Path(td) / "missing.db"
        rc = _mod.cmd_cost_store(_Args())
        assert rc == 2


# ────────────────────────────────────────────────────────────────
# langfuse subcommand
# ────────────────────────────────────────────────────────────────
def test_langfuse_auth_missing_env_returns_none():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("SOMETHING_ELSE=1\n")
        _mod.HOME = Path(td)
        assert _mod._langfuse_auth() is None


def test_langfuse_auth_reads_keys():
    import base64
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pubkey123\n"
                       "HERMES_LANGFUSE_SECRET_KEY=secret456\n")
        _mod.HOME = Path(td)
        auth = _mod._langfuse_auth()
        expected = base64.b64encode(b"pubkey123:secret456").decode()
        assert auth == expected


def test_check_langfuse_unverifiable_without_auth():
    with tempfile.TemporaryDirectory() as td:
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert len(checks) == 2
        assert checks[0][0] == "langfuse_auth"
        assert all(ok is None for _, ok, _ in checks)


def test_check_langfuse_traces_ok_auth_ok(monkeypatch):
    def fake_api(path, auth):
        assert "fromTimestamp" in path  # v3 API contract
        return {"data": [{"name": "job-x", "timestamp": "2026-08-27T00:00:00Z", "tags": []}]}
    monkeypatch.setattr(_mod, "_langfuse_api", fake_api)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert len(checks) == 2
        assert all(ok is True for _, ok, _ in checks)


def test_check_langfuse_api_down():
    def fake_api(path, auth):
        return {"error": "ConnectionRefused", "body": "refused"}
    _mod._langfuse_api = fake_api
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert checks[0][0] == "traces"
        assert checks[1][0] == "langfuse_auth"
        assert all(ok is False for _, ok, _ in checks)


def test_langfuse_exit_code_fail():
    _mod._langfuse_api = lambda path, auth: {"error": "down", "body": "down"}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        rc = _mod.cmd_langfuse(_Args())
        assert rc == 1


# ────────────────────────────────────────────────────────────────
# shared reporting
# ────────────────────────────────────────────────────────────────
def test_report_pass_json(capsys):
    rc = _mod._report(_Args(json_out=True), "cost-store", [
        ("a", True, "ok-a"), ("b", True, "ok-b"),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["overall"] == "PASS"
    assert out["subcommand"] == "cost-store"
    assert len(out["checks"]) == 2


def test_report_fail_text(capsys):
    rc = _mod._report(_Args(), "langfuse", [
        ("a", True, "ok"), ("b", False, "bad"),
    ])
    assert rc == 1
    out = capsys.readouterr().out
    assert "OVERALL: FAIL" in out
    assert "FAIL b: bad" in out


def test_report_unverifiable_exit_2():
    rc = _mod._report(_Args(), "cost-store", [
        ("a", None, "missing"), ("b", None, "missing2"),
    ])
    assert rc == 2


def test_main_unknown_subcommand_exits_2():
    import subprocess
    import sys as _sys
    proc = subprocess.run(
        [_sys.executable, str(_MANAGE / "fleet-hygiene.py"), "nope"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
