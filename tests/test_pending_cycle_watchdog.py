#!/usr/bin/env python3
"""Hermetic fault-injection suite for agent-pending-cycle-watchdog (O5-S1).

The watchdog mirrors cortex_doctor/checks.py's PENDING-cycle rules on a
schedule (every 6h, no_agent). This test proves the four behaviours the
doctor check only exercises on-demand:

  A: fresh PENDING + no live lock   -> LEAK alert (exit 1, named task)
  B: PENDING > 24h old (abandoned)  -> auto-resolved to MOVE_ON with note
  C: duplicate leak state           -> silent (StateTracker dedup gate)
  D: PENDING with a live lock       -> current task, NOT a leak (silent)
  E: clean DB                       -> silent, exit 0

Run:  python3 tests/test_pending_cycle_watchdog.py
Optional: PC_WATCHDOG_PATH=/path/to/agent-pending-cycle-watchdog.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_env = os.environ.get("PC_WATCHDOG_PATH")
WATCHDOG = Path(_env) if _env else (
    REPO / "ops" / "scripts" / "health" / "agent-pending-cycle-watchdog.py"
)
# The watchdog imports state_tracker + hermes_tz from the scripts dir
SCRIPTS_DIR = Path.home() / ".hermes-cortex" / "scripts"

SCHEMA = """
CREATE TABLE loop_cycles (
  id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, cycle_num INTEGER,
  spec_hash TEXT, code_hash TEXT, test_output_hash TEXT, completeness REAL,
  quality REAL, progress REAL, composite REAL, no_progress INTEGER,
  decision TEXT, user_overrode INTEGER, outcome_note TEXT,
  schema_version INTEGER, model_name TEXT, session_id TEXT
);
"""


def _mkdb(rows: list[tuple]) -> str:
    """Build a temp loop-governance DB with the given PENDING rows."""
    tmp = tempfile.mkdtemp(prefix="pc-watchdog-test-")
    db = str(Path(tmp) / "loop-governance.db")
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    now = datetime.utcnow()
    for task_id, age_h, session in rows:
        ts = (now - timedelta(hours=age_h)).isoformat()
        con.execute(
            "INSERT INTO loop_cycles (timestamp, task_id, cycle_num, decision, session_id) "
            "VALUES (?,?,?,?,?)",
            (ts, task_id, 1, "PENDING", session),
        )
    con.commit()
    con.close()
    return db


def _run(db: str, state_file: str) -> tuple[int, str]:
    """Run the watchdog against db; isolate its state file."""
    env = dict(os.environ)
    env["PENDING_DB_PATH"] = db
    env["PYTHONPATH"] = str(SCRIPTS_DIR)
    # Point the StateTracker at an isolated state dir so runs are independent
    env["CORTEX_HOME"] = os.path.dirname(state_file)
    # StateTracker resolves ~ via $HOME (Path.home()) — isolate it too, or
    # the test writes the REAL ~/.hermes-cortex/state/<name>.state and
    # dedup scenarios share fingerprints with live runs (2026-08-22).
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    env["HOME"] = os.path.dirname(state_file)
    proc = subprocess.run(
        [sys.executable, str(WATCHDOG)],
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    return proc.returncode, proc.stdout.strip()


def _decision(db: str, task_id: str) -> str:
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT decision, outcome_note FROM loop_cycles WHERE task_id=?",
        (task_id,),
    ).fetchone()
    con.close()
    return f"{row[0]}|{row[1] or ''}" if row else "MISSING"


def main() -> int:
    failures = []

    # A: fresh leak -> alert
    db = _mkdb([("leaky-task", 1, "sess-leak01")])
    rc, out = _run(db, "/tmp/pc-watchdog-state-a")
    if rc != 1 or "LEAK: leaky-task" not in out:
        failures.append(f"A leak alert: rc={rc} out={out!r}")

    # B: stale -> auto-resolve (decision flips, note attached)
    db = _mkdb([("abandoned-task", 30, "sess-stale01")])
    rc, out = _run(db, "/tmp/pc-watchdog-state-b")
    dec = _decision(db, "abandoned-task")
    if not dec.startswith("MOVE_ON|") or "auto-resolved" not in dec:
        failures.append(f"B stale auto-resolve: rc={rc} out={out!r} dec={dec!r}")

    # C: duplicate leak state -> silent on second run
    db = _mkdb([("leaky-task", 1, "sess-leak01")])
    rc1, _ = _run(db, "/tmp/pc-watchdog-state-c")
    rc2, out2 = _run(db, "/tmp/pc-watchdog-state-c")
    if rc1 != 1 or rc2 != 0 or out2 != "":
        failures.append(f"C dedup: rc1={rc1} rc2={rc2} out2={out2!r}")

    # D: current task (live lock) -> not a leak, silent
    db = _mkdb([("current-task", 1, "sess-cur01")])
    state_dir = tempfile.mkdtemp(prefix="pc-watchdog-lock-")
    os.makedirs(Path(state_dir) / "state", exist_ok=True)
    lock = Path(state_dir) / "state" / ".governance-lock-test.json"
    lock.write_text('{"task_id": "current-task", "status": "executing"}')
    env = dict(os.environ, PENDING_DB_PATH=db, CORTEX_HOME=state_dir,
               PYTHONPATH=str(SCRIPTS_DIR))
    proc = subprocess.run(
        [sys.executable, str(WATCHDOG)],
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    if proc.returncode != 0 or proc.stdout.strip() != "":
        failures.append(f"D current-task silent: rc={proc.returncode} out={proc.stdout.strip()!r}")

    # E: clean DB -> silent
    db = _mkdb([])
    rc, out = _run(db, "/tmp/pc-watchdog-state-e")
    if rc != 0 or out != "":
        failures.append(f"E clean silent: rc={rc} out={out!r}")

    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS — {WATCHDOG.name}: 5/5 scenarios (A leak, B stale, C dedup, D current, E clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
