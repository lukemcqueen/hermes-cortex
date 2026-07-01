#!/usr/bin/env python3
"""
agent-cron-failure-scanner.py — Scan ALL cron output directories for recent failures.

Scans ~/.hermes/cron/output/ for jobs that ran within the last 90 minutes
and shows an error indicator. Outputs a concise report to stdout.

Silent (no output, exit 0) when everything is clean.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

CRON_OUTPUT = Path.home() / ".hermes" / "cron" / "output"
LOOKBACK_MINUTES = 90
LOCAL_TZ = datetime.now().astimezone().tzinfo
NOW = datetime.now(LOCAL_TZ)
CUTOFF = NOW - timedelta(minutes=LOOKBACK_MINUTES)


def parse_timestamp_from_filename(fname: str) -> datetime | None:
    """Parse local-time timestamp from cron output filename like 2026-07-01_14-01-04.md"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})", fname)
    if not m:
        return None
    try:
        dt = datetime.strptime(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return None


def has_error_indicator(content: str) -> str | None:
    """Check if output content indicates a real failure. Returns a brief reason or None."""
    tail = "\n".join(content.split("\n")[-20:])

    # Check for explicit non-zero exit
    m = re.search(r"exit.*?code.*?[1-9]\b|exit.*?status.*?[1-9]\b", content, re.IGNORECASE)
    if m:
        return f"non-zero exit: {m.group(0).strip()[:80]}"

    # Check for Python tracebacks
    if re.search(r"Traceback \(most recent call last\)", content):
        return "Python traceback"

    # Check for error/fail in the last 20 lines
    err_lines = re.findall(r"^.*(?:ERROR|FAIL|FAILED|CRITICAL)\s.*$", tail, re.MULTILINE)
    if err_lines:
        return f"error/fail in recent output: {err_lines[0].strip()[:100]}"

    # Check for explicit failure patterns
    fail_patterns = [r"failed with", r"failed to", r"error:", r"error during",
                     r"cron job.*(?:failed|error)", r"exit code \d+", r"non.?zero"]
    for pat in fail_patterns:
        m = re.search(pat, tail, re.IGNORECASE)
        if m:
            return f"failure indicator: {m.group(0)[:80]}"

    return None


def main():
    if not CRON_OUTPUT.exists():
        return

    failures = []

    for job_dir in sorted(CRON_OUTPUT.iterdir()):
        if not job_dir.is_dir():
            continue

        # Get the most recent output file
        output_files = sorted(job_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not output_files:
            continue

        latest = output_files[0]
        ts = parse_timestamp_from_filename(latest.name)
        if ts is None or ts < CUTOFF:
            continue

        content = latest.read_text(encoding="utf-8", errors="replace")
        reason = has_error_indicator(content)
        if reason:
            failures.append({
                "job_id": job_dir.name,
                "file": latest.name,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": reason,
                "ago_min": int((NOW - ts).total_seconds() / 60),
            })

    if not failures:
        return

    print("# Cron Failure Scanner Report")
    print(f"# {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# Lookback: {LOOKBACK_MINUTES} minutes")
    print(f"# Failures found: {len(failures)}")
    print()

    for f in failures:
        print(f"## ❌ Job {f['job_id']}")
        print(f"- **File:** {f['file']}")
        print(f"- **When:** {f['timestamp']} ({f['ago_min']} min ago)")
        print(f"- **Issue:** {f['reason']}")
        print()


if __name__ == "__main__":
    main()