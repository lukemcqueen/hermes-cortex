#!/usr/bin/env python3
"""Scan cron output dirs for recent failures and send agent inbox alert.

Runs as a no_agent script every 30 min. Silent when all jobs healthy.
On failure: sends an inbox message to the agent with job name, error, and time.

Exit codes:
  0 - all healthy (no output)
  1 - failures found (output is the inbox message body)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
from hermes_tz import format_timestamp, get_timezone

# Import failure state for inbox alert dedup
# cron_failure_state.py is in ops/scripts/ (parent of agent/ directory)
_state_helper_dir = str(Path(__file__).resolve().parent.parent)
if _state_helper_dir not in sys.path:
    sys.path.insert(0, _state_helper_dir)
try:
    from cron_failure_state import FailureState
    _fs = FailureState("cron-failure-scanner")
except ImportError:
    _fs = None

CRON_OUTPUT = Path.home() / ".hermes" / "cron" / "output"
INBOX_API = os.environ.get(
    "AGENT_INBOX_URL",
    "http://127.0.0.1:8903/api/messages",
)
AGENT_NAME = os.environ.get("AGENT_NAME", "Joseph")
LOOKBACK_MINUTES = 90  # Check jobs that ran within the last 90 min


def get_latest_output(job_dir: Path) -> Tuple[Optional[datetime], str]:
    """Get the most recent output file and its content from a job dir."""
    files = sorted(job_dir.glob("*.md"), reverse=True)
    if not files:
        return None, ""
    latest = files[0]
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    content = latest.read_text(encoding="utf-8", errors="replace")
    return mtime, content


def extract_failure(content: str) -> Optional[str]:
    """Extract failure reason from cron output doc."""
    # Check for explicit failure markers
    if "**Status:** script failed" in content:
        # Extract stderr or the failure message
        stderr_match = re.search(r"stderr:\n(.+?)(?=\nstdout:|$)", content, re.DOTALL)
        if stderr_match:
            return stderr_match.group(1).strip()[:300]
        # Fallback: extract the first error-like line
        for line in content.split("\n"):
            if "error" in line.lower() or "traceback" in line.lower() or "exit code" in line.lower():
                return line.strip()[:200]
        return "Script failed (see output for details)"
    if "**Status:** silent (wakeAgent=false)" in content:
        return None  # Not a failure
    if "**Status:** silent (empty output)" in content:
        return None  # Not a failure
    return None


def main():
    if not CRON_OUTPUT.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
    failures = []

    for job_dir in sorted(CRON_OUTPUT.iterdir()):
        if not job_dir.is_dir():
            continue

        # Skip own output — prevents self-referential loop
        if job_dir.name in ("6f4afc3e62c8", "d4e93c159033"):
            continue

        mtime, content = get_latest_output(job_dir)
        if mtime is None or mtime < cutoff:
            continue  # Too old, skip

        # Try to get the job name from the content header
        name_match = re.search(r"# Cron Job: (.+)", content)
        job_name = name_match.group(1) if name_match else job_dir.name

        failure = extract_failure(content)
        if failure:
            failures.append((job_name, failure, mtime))

    if not failures:
        # Clear failure state — no active failures
        if _fs:
            _fs.record_success()
        return 0

    # ── Dedup: same failures within 60 min → stay silent ──────
    sigs = sorted(f"{n}:{r}" for n, r, _ in failures)
    sig_hash = FailureState.compute_hash("|".join(sigs)) if _fs else None
    if _fs and not _fs.should_report(sig_hash, cooldown_minutes=60):
        return 0  # Already reported this failure set recently

    # Build inbox message
    ts = format_timestamp("%Y-%m-%d %H:%M:%S %Z")
    lines = [f"⚠️ Cron failure scan @ {ts}", ""]
    for name, reason, when in failures:
        local_when = when.astimezone(get_timezone()).strftime("%H:%M:%S %Z")
        lines.append(f"• **{name}** ({local_when}): {reason}")

    body = "\n".join(lines)

    # Send inbox message to self
    body_with_topic = json.loads(body) if isinstance(body, str) else {}
    body_with_topic["topic"] = "system"
    payload = json.dumps({
        "to": AGENT_NAME,
        "subject": f"⚠️ Cron failures detected ({len(failures)} job(s))",
        "body": json.dumps(body_with_topic),
        "priority": "normal",
    })

    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", INBOX_API,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        print(f"Failed to send inbox alert: {e}", file=sys.stderr)
        return 1

    # Also print to stdout for cron output/delivery
    print(body)

    # Record failure report for dedup
    if _fs:
        _fs.record_failure(sig_hash, cooldown_minutes=60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
