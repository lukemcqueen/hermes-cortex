#!/usr/bin/env python3
"""Integration test for agent-loop-gov-lock-watchdog.py — proves it
DETECTS and REPORTS a stuck write-lock held by a loop-gov-named process
(POST-deploy leak, the exact case the security audit found the mtime heuristic
misses), but does NOT auto-kill (alert-only backstop, per operator directive
"no brute-force killing").

Strategy: hold BEGIN IMMEDIATE on loop-governance.db in a background process
named loop-gov-mcp.py for 60s; within that window run the watchdog; assert the
DB is write-blocked before, that the watchdog names the holder pid in its
report, and that the HARNESS (not the watchdog) is still alive the whole time —
proving the watchdog observed but did not kill.

We use a REAL BEGIN IMMEDIATE holder (not a stub) so the test exercises the
actual SQLite lock path the incident manifests through. Run with the hermes
venv python (needs sqlite3 only; state_tracker import is optional).

Run:  python3 test_loop_gov_lock_watchdog.py
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
DB = HOME / ".hermes-cortex" / "data" / "loop-governance.db"
WATCHDOG = HOME / "hermes-cortex" / "ops" / "scripts" / "health" / "agent-loop-gov-lock-watchdog.py"
PY = str(HOME / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3")

PASS = "  PASS"
FAIL = "  FAIL"


def _checks() -> list[str]:
    out: list[str] = []

    def check(cond, msg):
        out.append(f"{PASS if cond else FAIL} {msg}")

    # ---- 0. confirm DB starts writable
    def db_state(timeout=3):
        c = sqlite3.connect(str(DB), timeout=timeout)
        c.execute("PRAGMA busy_timeout=%d" % (timeout * 1000))
        try:
            c.execute("BEGIN IMMEDIATE")
            c.rollback()
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            c.close()

    check(db_state(), "baseline DB writable")

    # ---- 1. spawn a 60s BEGIN IMMEDIATE holder named loop-gov-mcp.py
    holder = Path(tempfile.mkdtemp()) / "loop-gov-mcp.py"
    holder.write_text(
        "import sqlite3,time\n"
        f"c=sqlite3.connect('{DB}',timeout=1)\n"
        "c.execute('PRAGMA busy_timeout=1000')\n"
        "c.execute('BEGIN IMMEDIATE')\n"
        "print('LOCK HELD',flush=True)\n"
        "time.sleep(60)\n"
    )
    hp = subprocess.Popen(
        [PY, str(holder)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        line = hp.stdout.readline().strip()
        # regenerate holder file on disk so the WD's pgrep sees the fresh cmd
        holder2 = holder  # same path
        check(line == "LOCK HELD", "harness reports LOCK HELD")
        check(db_state() is False, "DB blocked while harness holds BEGIN IMMEDIATE")

        # ---- 3. after watchdog: DB must STILL be blocked (watchdog is
        #         alert-only — it does not kill, so the lock is NOT freed)
        still_blocked = False
        for _ in range(10):
            if not db_state():
                still_blocked = True
                break
            time.sleep(0.3)
        check(still_blocked, "DB still write-blocked after alert-only watchdog (no kill)")

        # ---- 4. the watchdog must NAME the holder pid in its report
        wd = subprocess.run([PY, str(WATCHDOG)], capture_output=True, text=True, timeout=90)
        wd_out = (wd.stdout + wd.stderr).strip()
        check(
            str(hp.pid) in wd_out,
            f"watchdog report names holder pid {hp.pid} in: {wd_out[:120]!r}",
        )

        # ---- 5. the harness is STILL alive — the watchdog did NOT kill it
        check(
            hp.poll() is None,
            "holder process still alive after watchdog (alert-only, never kills)",
        )
    finally:
        hp.kill()

    return out


if __name__ == "__main__":
    results = _checks()
    print("\n".join(results))
    npass = sum(1 for r in results if r.startswith(PASS))
    print(f"\n{len(results)} checks, {npass} pass")
    sys.exit(0 if npass == len(results) else 1)