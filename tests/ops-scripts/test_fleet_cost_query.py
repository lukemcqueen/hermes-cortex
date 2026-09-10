"""Fleet-cost-query.py — behavior contract tests (real subprocess, temp DB)."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "scripts" / "manage" / "fleet-cost-query.py"


def _make_db(home: Path, rows):
    cron = home / ".hermes" / "cron"
    cron.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(cron / "cron-costs.db"))
    db.execute(
        "CREATE TABLE cron_runs (run_time TEXT, model TEXT, estimated_cost_usd REAL, "
        "input_tokens INTEGER, output_tokens INTEGER, job_id TEXT)"
    )
    db.executemany("INSERT INTO cron_runs VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    db.close()


def _run_with_home(home: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "HOME": str(home)},
    )


def test_outputs_json_summary_from_real_db(tmp_path):
    _make_db(tmp_path, [
        ("2026-09-09T10:00:00", "deepseek-v4-flash", 0.5, 100, 200, "job-a"),
        ("2026-09-09T11:00:00", "glm-5.3-flash", 0.25, 50, 75, "job-b"),
    ])
    r = _run_with_home(tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["total_cost_usd"] == 0.75
    assert data["recent_30d_runs"] == 2
    assert {m["model"] for m in data["by_model"]} == {"deepseek-v4-flash", "glm-5.3-flash"}
    assert data["top_5_jobs"][0]["cost"] == 0.5  # job-a is top


def test_missing_db_fails_soft_with_marker(tmp_path):
    r = _run_with_home(tmp_path)
    assert r.returncode == 0  # soft fail — fleet dispatch must not break
    data = json.loads(r.stdout)
    assert data["error"] == "NO_COST_DB"
    assert isinstance(data.get("host"), str) and data["host"]


def test_zero_cost_rows_excluded_from_by_model(tmp_path):
    _make_db(tmp_path, [("2026-09-09T10:00:00", "free-model", 0.0, 10, 20, "job-x")])
    r = _run_with_home(tmp_path)
    data = json.loads(r.stdout)
    assert data["by_model"] == []  # WHERE estimated_cost_usd > 0
    assert data["total_cost_usd"] == 0.0
    # daily has NO cost filter — a zero-cost run still counts as a day entry
    assert data["daily_30d"] == [{"day": "2026-09-09", "cost": 0}]


def test_old_rows_outside_30d_window_excluded_from_recent(tmp_path):
    _make_db(tmp_path, [
        ("2026-01-01T10:00:00", "old-model", 9.0, 1, 1, "job-old"),
        ("2026-09-09T10:00:00", "new-model", 1.0, 1, 1, "job-new"),
    ])
    r = _run_with_home(tmp_path)
    data = json.loads(r.stdout)
    assert data["total_cost_usd"] == 10.0  # total includes everything
    assert data["recent_30d_usd"] == 1.0   # 30d window excludes job-old