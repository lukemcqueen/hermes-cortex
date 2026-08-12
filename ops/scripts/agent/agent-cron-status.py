#!/usr/bin/env python3
"""agent-cron-status.py — read-only dump of cron status + health-push error log.

Purpose: identify why the health-vector "no_errored_crons" check (index [2])
reports -1 on a fleet host. Two sources feed that flag:

  1. jobs.json — an enabled job with last_status == "error" (server agents
     running health-vector.py read this directly).
  2. health-push-errors.log — the health-vector-push.sh check flags -1 when
     ~/.hermes-cortex/logs/health-push-errors.log is non-empty (client
     agents: joseph, kustos, gisu, titus). NOTE: pre-2026-08-12 the check had
     no recency bound, so one historical push failure poisoned the flag
     forever; fixed to require a modification within the last 6h.

Deployed to every agent via cortex-update.sh so the orchestrator can EXEC it
on any fleet host to name the failing source — no guessing or hand-reading
remote files.

Exit codes:
  0 — healthy (no enabled job with last_status == error, and the push-error
      log has no entry newer than 6h)
  1 — at least one enabled job has last_status == error, OR the push-error
      log was modified within the last 6h (output is the dump)
  2 — jobs.json missing/unreadable (output is the error)

Output: one line per job, TAB-separated:
  name  enabled  schedule  last_status  last_run_at  last_error
followed by a push-log section:
  # push_log: <path>  exists=<0|1>  size=<bytes>  mtime=<iso>  recent_6h=<0|1>
  # push_log tail (last 5 lines)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

JOBS_FILE = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "cron" / "jobs.json"
PUSH_LOG = Path(os.path.expanduser("~/.hermes-cortex/logs/health-push-errors.log"))
RECENT_MINUTES = 360  # match health-vector-push.sh recency bound (6h)


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

    # ── Push-error log (client-agent source of the no_errored_crons flag) ──
    print()
    if PUSH_LOG.exists():
        try:
            size = PUSH_LOG.stat().st_size
            mtime = datetime.fromtimestamp(PUSH_LOG.stat().st_mtime, tz=timezone.utc)
            age_min = (datetime.now(timezone.utc) - mtime).total_seconds() / 60.0
            recent = age_min <= RECENT_MINUTES
            if recent:
                errored = True
            print(
                f"# push_log: {PUSH_LOG}  exists=1  size={size}  "
                f"mtime={mtime.isoformat()}  recent_{RECENT_MINUTES // 60}h={1 if recent else 0}"
            )
            tail = PUSH_LOG.read_text(encoding="utf-8", errors="replace").strip().split("\n")[-5:]
            for ln in tail:
                print(f"#   {ln[:200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"# push_log: {PUSH_LOG}  ERROR reading: {exc}")
    else:
        print(f"# push_log: {PUSH_LOG}  exists=0")

    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
