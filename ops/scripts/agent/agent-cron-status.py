#!/usr/bin/env python3
"""agent-cron-status.py — read-only dump of cron job status from jobs.json.

Purpose: identify which cron job(s) have last_status == "error" (the signal
behind the health-vector "no_errored_crons" check, index [2]). Deployed to
every agent via cortex-update.sh so the orchestrator can EXEC it on any
fleet host to name the failing job — no need to guess or read the remote
file by hand.

Exit codes:
  0 — healthy (no enabled job with last_status == error), output is the dump
  1 — at least one enabled job has last_status == error (output is the dump)
  2 — jobs.json missing/unreadable (output is the error)

Output: one line per job, TAB-separated:
  name  enabled  schedule  last_status  last_run_at  last_error
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

JOBS_FILE = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "cron" / "jobs.json"


def main() -> int:
    if not JOBS_FILE.exists():
        print(f"jobs.json not found: {JOBS_FILE}", file=sys.stderr)
        return 2
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 — report any read/parse failure
        print(f"jobs.json unreadable: {exc}", file=sys.stderr)
        return 2

    jobs = data if isinstance(data, list) else data.get("jobs", [])
    if not isinstance(jobs, list):
        print(f"jobs.json unexpected structure: {type(data).__name__}", file=sys.stderr)
        return 2

    errored = False
    print("name\tenabled\tschedule\tlast_status\tlast_run_at\tlast_error")
    for j in sorted(jobs, key=lambda x: str(x.get("name", ""))):
        name = j.get("name", "?")
        enabled = j.get("enabled", True)
        status = j.get("last_status", "")
        if enabled and status == "error":
            errored = True
        err = j.get("last_error", "") or ""
        err_one = err.replace("\t", " ").replace("\n", " ")[:160]
        print(
            f"{name}\t{enabled}\t{j.get('schedule', '')}\t{status}\t"
            f"{j.get('last_run_at', '')}\t{err_one}"
        )

    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
