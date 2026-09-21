#!/usr/bin/env python3
"""agent-cron-failure-watchdog.py — pause crons that fail N times in a row.

no_agent watchdog. Reads ~/.hermes/cron/jobs.json each tick, tracks
consecutive `last_status: error` per job in a state file, and after
CONSECUTIVE_FAILURE_LIMIT (default 3) consecutive failures:

  - prints an ALERT to stdout (delivered to the cron's configured channel)
  - pauses the job via `hermes cron pause <job_id>` so it stops re-firing

SILENT (empty stdout) when every job is healthy or below the threshold —
classic watchdog pattern.

Why this exists: agent-push-metrics failed 1053 consecutive runs
(2026-08-30..09-14) with no counter, no auto-pause, and no re-alert — the
remediation sensor dedups to silence after the first report and nothing
ever paused the failing cron. A job that fails for a quarter-hour should
STOP and tell the operator, not burn 1000+ ticks retrying an unfixable
sink. Transient failures (1-2 ticks) stay silent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CRON_JOBS_FILE = HOME / ".hermes" / "cron" / "jobs.json"
STATE_FILE = HOME / ".hermes-cortex" / "state" / "cron-failure-watchdog.json"

# The watchdog's own cron job name — it must never evaluate/count/pause ITSELF.
# When it pauses a broken cron it exits 1 (to deliver the alert), which sets its
# OWN last_status=error; counting that would accumulate 3 self-errors and pause
# itself — the observed fleet-wide self-pause cascade.
OWN_JOB_NAME = "agent-cron-failure-watchdog"

CONSECUTIVE_FAILURE_LIMIT = 3  # consecutive errors before alert + pause


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _pause_job(job_id: str) -> bool:
    """Pause the cron via the hermes CLI. Returns True on success."""
    try:
        r = subprocess.run(
            ["hermes", "cron", "pause", job_id],
            capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception as exc:
        print(f"⚠️  Failed to pause cron {job_id}: {exc}", file=sys.stderr)
        return False


def _evaluate(jobs: list[dict], limit: int = CONSECUTIVE_FAILURE_LIMIT) -> tuple[list[str], list[str]]:
    """Count consecutive errors per job; return (alerts, job_ids_to_pause).

    Rules:
      - paused or disabled jobs are skipped entirely (not counted)
      - last_status == "error" increments the counter
      - any other last_status (ok, None, ...) resets it to 0
      - crossing the limit: one alert + one pause request per incident
      - already-alerted incidents stay silent until the counter resets
    """
    state = _load_state()
    alerts: list[str] = []
    to_pause: list[str] = []
    now = _now_iso()

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if not job_id:
            continue
        if str(job.get("name") or "").strip() == OWN_JOB_NAME:
            # Never monitor/count/pause ourselves — see OWN_JOB_NAME docstring.
            continue
        if job.get("paused_at") or not job.get("enabled", True):
            continue

        status = job.get("last_status", "")
        entry = state.setdefault(str(job_id), {
            "consecutive": 0, "alerted": False,
        })

        if status == "error":
            entry["consecutive"] += 1
            if entry["consecutive"] >= limit and not entry["alerted"]:
                name = job.get("name") or job_id
                alerts.append(
                    f"🔴 Cron '{name}' failed "
                    f"{entry['consecutive']} consecutive runs — pausing it "
                    f"({now}). Fix the root cause, then `hermes cron resume "
                    f"{job_id}`."
                )
                entry["alerted"] = True
                to_pause.append(str(job_id))
        else:
            # Any non-error status (ok, None, ...) = the cron is healthy now.
            # Reset the counter/alarm so a NEW failure streak re-alerts. This is
            # deliberately SILENT: a recovered cron is a success, and emitting it
            # as an alert (exit 1) used to mark the watchdog's OWN last_status=error
            # and cascade into self-pause.
            if entry["consecutive"] or entry["alerted"]:
                entry["consecutive"] = 0
                entry["alerted"] = False

    _save_state(state)
    return alerts, to_pause


def run_once() -> int:
    if not CRON_JOBS_FILE.exists():
        return 0
    try:
        data = json.loads(CRON_JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    jobs = data if isinstance(data, list) else data.get("jobs", [])

    alerts, to_pause = _evaluate(jobs)

    for job_id in to_pause:
        _pause_job(job_id)

    if alerts:
        print("\n\n".join(alerts))
        return 1  # delivery: alert output goes to the cron channel
    return 0  # silent when healthy


if __name__ == "__main__":
    sys.exit(run_once())