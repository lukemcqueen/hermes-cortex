"""Regression test: in-process SQLite write-lock recovery for begin_change.

Incident class (2026-09-29): a loop-gov MCP daemon spawned BEFORE a deploy held
an uncommitted write transaction on ~/.hermes-cortex/data/loop-governance.db.
begin_change then failed with "database is locked" for every session, and write
tools were gated behind the very lock that could not be acquired (the
enforcement-gate-integrity catch-22). Recovery = kill the stale holder daemon;
the death supervisor respawns a clean one and begin_change re-acquires.

This test asserts the boundary behavior at the lock layer (adversarial
ADV-2876-1): it does NOT launch/kill the MCP daemon or assert supervisor
respawn — it is an in-process SQLite-lock recovery regression test, driving
begin_change/end_change directly:

  1. open a temp loop-governance DB under a subprocess holding BEGIN IMMEDIATE
  2. begin_change with a holder active  -> REFUSED with "database is locked"
     (fail-closed: nothing acquires while a writer is stuck)
  3. kill the holder                     -> write lock released
  4. begin_change again                  -> acquires; end_change releases

The daemon-supervisor-respawn half is exercised operationally (kill the stale
daemon, gateway respawns it); this test pins the lock-recovery contract that the
daemon relies on. Hermetic: uses a temp GOVERNANCE_STATE_DIR + LOOP_DB, never
the real DB.
Run:  /home/moses/.hermes/hermes-agent/venv/bin/python3 tests/test_loop_gov_db_lock_recovery.py
"""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"

_FAIL = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        _FAIL.append(name)
        print(f"  FAIL  {name} — {detail}")


def _load_module(state_dir, loop_db):
    spec = importlib.util.spec_from_file_location(
        f"lgm_{os.urandom(4).hex()}", _MCP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.GOVERNANCE_STATE_DIR = Path(state_dir)
    mod.LOOP_DB = Path(loop_db)
    return mod


def _hold_begin_immediate(db_path):
    """Spawn a child that holds an exclusive write transaction on the temp DB."""
    code = f"""
import sqlite3, time, sys
c = sqlite3.connect({str(db_path)!r}, timeout=5)
c.execute("PRAGMA journal_mode=WAL")
c.execute("BEGIN IMMEDIATE")   # acquire the write lock and HOLD it
sys.stderr.write("HOLDING\\n"); sys.stderr.flush()
time.sleep(60)
"""
    p = subprocess.Popen([sys.executable, "-c", code],
                         stderr=subprocess.PIPE, text=True)
    # wait until the child signals it holds the lock
    line = p.stderr.readline().strip()
    assert line == "HOLDING", f"holder did not acquire: {line!r}"
    return p


def main():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state = td / "state"; state.mkdir()
        db = td / "loop.db"

        mod = _load_module(state, db)

        # 1) No holder: begin_change acquires normally (baseline).
        r = mod._begin_change({"task_id": "t0",
                               "description": "baseline acquire",
                               "session_id": "sess_baseline"})
        check("baseline begin_change acquires", "Governance session started" in r.content[0].text,
              r.content[0].text[:100])
        mod._end_change({"task_id": "t0", "session_id": "sess_baseline"})

        # 2) Stale holder present: begin_change must REFUSE (fail closed).
        holder = _hold_begin_immediate(db)
        try:
            r = mod._begin_change({"task_id": "t1",
                                   "description": "should be blocked by holder",
                                   "session_id": "sess_blocked"})
            t = r.content[0].text
            check("begin_change REFUSED while holder active", "database is locked" in t,
                  t[:120])
        finally:
            # 3) Kill the stale holder (the recovery action).
            holder.send_signal(signal.SIGTERM)
            holder.wait(timeout=10)

        # verify the write lock is released (assert the actual result)
        import sqlite3 as _s
        c = _s.connect(str(db), timeout=5)
        c.execute("PRAGMA busy_timeout=5000")
        try:
            c.execute("BEGIN IMMEDIATE")
            lock_free = True
            c.rollback()
        except _s.OperationalError:
            lock_free = False
        finally:
            c.close()
        check("write lock released after holder killed", lock_free,
              "BEGIN IMMEDIATE still failed after kill")

        # 4) begin_change re-acquires after the kill (the actual recovery).
        r = mod._begin_change({"task_id": "t2",
                               "description": "reacquire after holder killed",
                               "session_id": "sess_recover"})
        t = r.content[0].text
        check("begin_change re-acquires after holder killed",
              "Governance session started" in t, t[:100])
        mod._end_change({"task_id": "t2", "session_id": "sess_recover"})

    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
