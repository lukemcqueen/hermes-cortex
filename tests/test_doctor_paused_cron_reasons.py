#!/usr/bin/env python3
"""A paused cron with no recorded reason must be REPORTED, not read as normal.

The gap this closes (2026-10-14): `hermes cron pause <id>` takes no reason, so two
auto-pauses by agent-cron-failure-watchdog and one hand pause left three jobs with an
empty `paused_reason` — and an operator reading the cron list could not tell a
deliberate stop from an abandoned job. The check accepts a reason from either
sanctioned store (jobs.json `paused_reason`, or the job's durable notepad) and WARNS
on a paused job that has neither.

Driven BOTH ways with fixtures: explained jobs must NOT warn, and an unexplained one
must be named. Never against the live host's cron state, which would flap the moment
someone pauses a job.

Run: python3 -m pytest tests/test_doctor_paused_cron_reasons.py -q
"""

import importlib
import json
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))


class _Result:
    def __init__(self):
        self.rows = []

    def add(self, name, status, detail="", fix=""):
        self.rows.append({"name": name, "status": status, "detail": detail, "fix": fix})

    def status(self):
        return self.rows[-1]["status"]

    def detail(self):
        return self.rows[-1]["detail"]

    def fix(self):
        return self.rows[-1]["fix"]


def _checks():
    """Import the REPO's ``cortex_doctor.checks`` deterministically.

    A plain ``import_module`` is not enough: another suite on the same run can leave a
    ``cortex_doctor`` package cached from the DEPLOYED tree (which lacks a check not yet
    deployed), and the tests then fail with "module has no attribute ..." - a verdict
    that depends on WHO invoked them. Drop the cached package and put the repo's manage
    dir first, so this test measures the source it ships with.
    """
    manage = str(_REPO / "ops" / "scripts" / "manage")
    while manage in sys.path:
        sys.path.remove(manage)
    sys.path.insert(0, manage)
    for name in [n for n in sys.modules if n == "cortex_doctor" or n.startswith("cortex_doctor.")]:
        del sys.modules[name]
    return importlib.import_module("cortex_doctor.checks")


def _host(tmp_path, jobs, notepad_rows=None):
    """Point the check at a fixture jobs.json (+ optional notepad.db)."""
    c = _checks()
    hermes_home = tmp_path / "hermes"
    (hermes_home / "cron").mkdir(parents=True, exist_ok=True)
    jobs_file = hermes_home / "cron" / "jobs.json"
    jobs_file.write_text(json.dumps({"jobs": jobs}))
    if notepad_rows:
        db = hermes_home / "cron" / "notepad.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cron_notepad (job_id TEXT, key TEXT, value TEXT, updated_at TEXT)")
        con.executemany("INSERT INTO cron_notepad VALUES (?,?,?,?)", notepad_rows)
        con.commit()
        con.close()
    c.JOBS_FILE = jobs_file
    c.HERMES_HOME = hermes_home
    return c


def _paused(job_id="job-1", name="agent-something", reason=None, enabled=False):
    return {"id": job_id, "name": name, "enabled": enabled,
            "paused_at": "2026-09-23T03:51:03+09:00", "paused_reason": reason}


def test_no_paused_jobs_is_a_pass(tmp_path):
    c = _host(tmp_path, [{"id": "j", "name": "agent-ok", "enabled": True}])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "PASS", res.rows
    assert "no paused crons" in res.detail()
    print("  no paused crons -> PASS ✓")


def test_a_jobs_json_reason_is_accepted(tmp_path):
    c = _host(tmp_path, [_paused(reason="paused on the operator's directive")])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "PASS", res.rows
    print("  a jobs.json paused_reason is accepted ✓")


def test_a_notepad_reason_is_accepted_without_a_jobs_json_reason(tmp_path):
    """The auto-pause path: the CLI cannot set paused_reason, so the watchdog records
    it in the notepad instead."""
    c = _host(tmp_path, [_paused()],
              notepad_rows=[("job-1", "paused_reason", "failed 3 consecutive runs", "now")])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "PASS", res.rows
    print("  a notepad paused_reason alone is accepted ✓")


def test_a_reasonless_pause_is_reported_and_named(tmp_path):
    c = _host(tmp_path, [_paused(job_id="job-x", name="agent-silent-pause")])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "WARN", res.rows
    assert "agent-silent-pause" in res.detail(), res.detail()
    assert "NO recorded reason" in res.detail(), res.detail()
    assert "hermes cron notepad" in res.fix() and "hermes cron resume" in res.fix(), res.fix()
    print("  an unexplained pause is WARNed and named, with a runnable fix ✓")


def test_a_disabled_job_counts_as_paused(tmp_path):
    """enabled=false without paused_reason is the same ambiguity from the other field."""
    c = _host(tmp_path, [{"id": "job-d", "name": "agent-disabled",
                          "enabled": False, "paused_at": None, "paused_reason": None}])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "WARN", res.rows
    assert "agent-disabled" in res.detail()
    print("  enabled=false with no reason is also reported ✓")


def test_a_blank_reason_does_not_count(tmp_path):
    c = _host(tmp_path, [_paused(reason="   ")])
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() == "WARN", res.rows
    print("  a whitespace-only reason does not count as an explanation ✓")


def test_the_live_host_reports_a_status_without_crashing():
    """The real check reads the real stores — smoke only, no assertion on the verdict
    (a WARN here is a finding about the host, not a test failure)."""
    c = _checks()
    res = _Result()
    c.check_paused_cron_reasons(res)
    assert res.status() in {"PASS", "WARN", "INFO"}, res.rows
    print(f"  live host -> {res.status()}: {res.detail()[:70]} ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
