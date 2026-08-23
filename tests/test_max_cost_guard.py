#!/usr/bin/env python3
"""Hermetic tests for max_cost_guard.py (O6-S1 MAX_COST pre-fire guard).

Covers: p95+headroom cap computation, today-spend block verdict, fail-open
on insufficient history, orch-* exemption, and no-data allow. Uses a temp
SQLite DB — no live state touched.
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage"))
import max_cost_guard as g


def _make_db():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tf.close()
    conn = sqlite3.connect(tf.name)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE cron_runs (
        id INTEGER PRIMARY KEY, job_id TEXT, run_time TEXT,
        estimated_cost_usd REAL, no_agent INTEGER)""")
    return conn, tf.name


def test_cap_and_block():
    conn, path = _make_db()
    try:
        for i in range(10):
            conn.execute(
                "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
                "VALUES (?, ?, ?, 0)",
                ("testjob", f"2026-08-{10+i:02d}T00:00:00Z", 0.10),
            )
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES ('testjob', ?, 0.10, 0)", (f"{day}T01:00:00Z",))
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES ('testjob', ?, 0.10, 0)", (f"{day}T02:00:00Z",))
        conn.commit()

        cap = g.compute_cap("testjob", conn)
        assert cap == 0.20, f"cap expected 0.20, got {cap}"
        d = g.should_fire("testjob", conn=conn)
        assert d["decision"] == "block", f"expected block, got {d}"
        assert d["today_spend"] >= d["cap"], f"spend {d['today_spend']} >= cap {d['cap']}"
    finally:
        conn.close()
        os.unlink(path)


def test_fail_open_insufficient():
    conn, path = _make_db()
    try:
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES ('newjob', '2026-08-20T00:00:00Z', 0.05, 0)")
        conn.commit()
        d = g.should_fire("newjob", conn=conn)
        assert d["decision"] == "allow", f"expected allow (insufficient), got {d}"
        assert d["cap"] is None
    finally:
        conn.close()
        os.unlink(path)


def test_orch_exempt():
    conn, path = _make_db()
    try:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO cron_runs (job_id, run_time, estimated_cost_usd, no_agent) "
            "VALUES ('orch-test', ?, 0.50, 0)", (f"{day}T01:00:00Z",))
        conn.commit()
        d = g.should_fire("orch-test", "orch-test", conn=conn)
        assert d["decision"] == "allow", f"expected allow (orch exempt), got {d}"
        assert "exempt" in d["reason"]
    finally:
        conn.close()
        os.unlink(path)


def test_no_data_allow():
    conn, path = _make_db()
    try:
        d = g.should_fire("nonexistent", conn=conn)
        assert d["decision"] == "allow", f"expected allow (no data), got {d}"
    finally:
        conn.close()
        os.unlink(path)


def test_p95_nearest_rank():
    assert g._p95([0.1] * 10) == 0.1
    assert g._p95([0.01, 0.02, 0.03, 0.04]) == 0.04  # int(0.95*4)=3 -> idx 3
    assert g._p95([0.5]) == 0.5


if __name__ == "__main__":
    for fn in (test_cap_and_block, test_fail_open_insufficient, test_orch_exempt,
               test_no_data_allow, test_p95_nearest_rank):
        fn()
        print(f"  OK {fn.__name__}")
    print("ALL MAX_COST GUARD TESTS PASSED")
