#!/usr/bin/env python3
"""The soul-refinement extraction script must stay re-runnable (no pytest needed).

    python3 tests/test_extract_human_messages.py     # exit 0 = pass

The 2026-10-07 soul-refinement report makes a load-bearing claim — "54 user
rows, 30 human, 3 sessions" — sourced from docs/reviews/extract-human-messages.py.
A report whose evidence script silently stops working is worse than no report:
the number looks authoritative and can't be reproduced. This asserts the script
exists, runs against the live store, and applies its scaffolding filter.

Skips (exit 0) when ~/.hermes/state.db is absent — the script is host-specific
and the repo is shared across hosts.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "reviews" / "extract-human-messages.py"
DB = Path(os.path.expanduser("~/.hermes/state.db"))
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def main():
    check(SCRIPT.exists(), f"missing extraction script: {SCRIPT}")
    if failures:
        return report()

    text = SCRIPT.read_text()
    check("mode=ro" in text, "script must open the sessions store read-only (mode=ro)")
    check("query_only=1" in text, "script must set PRAGMA query_only=1")
    check("[IMPORTANT:" in text, "script must filter cron scaffolding")

    if not DB.exists():
        print(f"SKIP: {DB} absent on this host — script is host-specific")
        return 0

    # Real run: the script must exit 0 and print its summary line.
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "2026-10-07"],
        capture_output=True, text=True, timeout=120,
    )
    check(proc.returncode == 0, f"script exited {proc.returncode}: {proc.stderr[:400]}")
    check("user_rows=" in proc.stdout, "script must print a user_rows= summary")
    check("human_rows=" in proc.stdout, "script must print a human_rows= summary")
    check("sessions_with_human=" in proc.stdout, "script must print a sessions summary")
    out = Path(SCRIPT).parent / "user_msgs.json"
    check(out.exists(), "script must write user_msgs.json beside itself")
    return report()


def report():
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: extraction script is re-runnable and read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
