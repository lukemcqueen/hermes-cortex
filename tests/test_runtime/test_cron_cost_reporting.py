"""cron-cost-metrics.py + orch-weekly-cost-report.py — per-cron cost series and the weekly report.

Why this exists (story c579ef95 [cost/3]): the fleet knows its TOKENS (per-cron
`usage_audit.jsonl`) and, since 2026-10-06, no longer stores a price table at all —
a stored price rots on every provider hike, which is why the `cron-costs.db` stack
was deleted. The durable spend truth is Hermes' own `state.db` -> `sessions`
(`estimated_cost_usd`, written live at current prices, cron rows named
`cron_<jobid>_<ts>`).

Two properties are load-bearing and are what these tests pin:

  1. a number that cannot be read is OMITTED and declared unavailable
     (`hermes_cron_cost_available 0` / a `NO DATA` coverage line) —
     never a fabricated 0, and never an alert built on no data;
  2. the weekly report alerts (rc=1) only from MEASURED data, and says which
     hosts are unmeasured instead of extrapolating.

Everything is driven through the scripts' own CLI against temp fixtures:
no live audit log, no live state.db, no real governance store. Fixture times are
relative to now, because the report windows on the clock.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
METRICS = REPO / "ops" / "scripts" / "manage" / "cron-cost-metrics.py"
REPORT = REPO / "ops" / "scripts" / "manage" / "orch-weekly-cost-report.py"

AGENT = "test-agent"


def _audit(tmp: Path, rows) -> Path:
    p = tmp / "usage_audit.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _sessions_db(tmp: Path, rows) -> Path:
    """Minimal stand-in for ~/.hermes/state.db's `sessions` table.

    Column names mirror the LIVE schema (verified 2026-10-22): the key is `id`
    — there is no `session_id` column. A fixture that invents one keeps a wrong
    query green, which is exactly how the first version of this generator
    shipped a read that never matched a single row.
    """
    p = tmp / "state.db"
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL,"
        " input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL)"
    )
    con.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return p


def _run(script: Path, *args, env_extra=None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script), *args], env=env, capture_output=True, text=True, timeout=120
    )


def _value(stdout: str, metric_fragment: str) -> float:
    """Last whitespace-separated field of the first line carrying this fragment."""
    for line in stdout.splitlines():
        if metric_fragment in line and not line.startswith("#"):
            return float(line.split()[-1])
    raise AssertionError(f"no series line carrying {metric_fragment!r} in:\n{stdout}")


# ── the generator ────────────────────────────────────────────────────────────

def test_tokens_are_summed_per_job_and_fires_counted(tmp_path):
    audit = _audit(
        tmp_path,
        [
            {"job_id": "jobA", "total_tokens": 120},
            {"job_id": "jobA", "total_tokens": 80},
            {"job_id": "jobB", "total_tokens": 5},
        ],
    )
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(audit))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"}') == 200
    assert _value(r.stdout, 'hermes_cron_fires_total{agent="test-agent",job_id="jobA"}') == 2
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobB"}') == 5


def test_spend_comes_from_the_sessions_table(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_t1", "cron", 1.0, 100, 10, 0.25),
            ("cron_jobA_t2", "cron", 2.0, 100, 10, 0.15),
            ("cli_t3", "cli", 3.0, 100, 10, 9.99),  # not cron — must not be counted
        ],
    )
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(audit), "--state-db", str(db))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_cost_usd{agent="test-agent",job_id="jobA"}') == 0.4
    assert _value(r.stdout, 'hermes_cron_cost_usd_total{agent="test-agent"}') == 0.4
    assert _value(r.stdout, 'hermes_cron_cost_available{agent="test-agent"}') == 1


def test_unreadable_spend_is_declared_unavailable_never_zero(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    r = _run(
        METRICS,
        "--prometheus",
        "--agent",
        AGENT,
        "--audit",
        str(audit),
        "--state-db",
        str(tmp_path / "missing.db"),
    )
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_cost_available{agent="test-agent"}') == 0
    assert "hermes_cron_cost_usd{" not in r.stdout, "an unreadable spend source must not emit a value"
    assert "unavailable" in r.stderr


def test_malformed_audit_lines_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "usage_audit.jsonl"
    p.write_text('{"job_id": "jobA", "total_tokens": 7}\nnot json at all\n[1,2]\n')
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(p))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"}') == 7


def test_no_source_at_all_is_its_own_outcome(tmp_path):
    r = _run(
        METRICS,
        "--prometheus",
        "--agent",
        AGENT,
        "--audit",
        str(tmp_path / "absent.jsonl"),
        "--state-db",
        str(tmp_path / "absent.db"),
    )
    assert r.returncode == 2, "nothing readable must not look like a successful empty push"
    assert r.stdout.strip() == ""
    assert "no readable source" in r.stderr, "and it must say what it could not read"


def test_missing_agent_name_is_refused(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1}])
    r = _run(METRICS, "--prometheus", "--agent", "", "--audit", str(audit))
    assert r.returncode == 2
    assert "AGENT_NAME" in r.stderr, "misattributed cost metrics are worse than none"


# ── the weekly report ────────────────────────────────────────────────────────

def test_weekly_report_alerts_above_the_daily_target(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1000}])
    now = time.time()
    # two measured days, 12.00 and 14.00 -> average 13.00 > 10
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_d1", "cron", now, 1, 1, 12.0),
            ("cron_jobA_d2", "cron", now - 86400, 1, 1, 14.0),
        ],
    )
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 1, "a breach must be a failed run, not a quiet line"
    assert "FLEET COST ABOVE TARGET" in r.stdout
    assert "13.00" in r.stdout, "the alert must carry the measured average"


def test_weekly_report_is_quiet_below_the_daily_target(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1000}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 1.5)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FLEET COST ABOVE TARGET" not in r.stdout
    assert "1.50" in r.stdout


def test_weekly_report_target_is_configurable(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 3.0)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7",
             env_extra={"CORTEX_COST_DAILY_TARGET_USD": "2"})
    assert r.returncode == 1
    assert "FLEET COST ABOVE TARGET" in r.stdout


def test_weekly_report_without_spend_data_says_no_data_and_does_not_alert(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    r = _run(
        REPORT,
        "--audit",
        str(audit),
        "--state-db",
        str(tmp_path / "missing.db"),
        "--days",
        "7",
    )
    assert r.returncode == 0, "no data is not a breach"
    assert "NO DATA" in r.stdout
    assert "FLEET COST ABOVE TARGET" not in r.stdout


def test_weekly_report_ignores_sessions_outside_the_window(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_in", "cron", time.time(), 1, 1, 1.0),
            ("cron_jobA_out", "cron", time.time() - 40 * 86400, 1, 1, 999.0),
        ],
    )
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 0, r.stdout
    assert "1.00" in r.stdout and "999" not in r.stdout, "the window filter is what makes the number"


def test_weekly_report_states_what_is_not_measured(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 1.0)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert "COVERAGE" in r.stdout
    assert "cost/4" in r.stdout, "the unmeasured worker hosts must be named, not extrapolated"
