#!/usr/bin/env python3
"""Hermetic suite for agent-review-queue-sweep (O5/G-5).

Proves the stale-sweep + triage contract against a temp loop-governance DB:

  A: STOP-ok older than the age cutoff, clean note      -> closed (accepted)
  B: STOP-ok younger than the cutoff                    -> NOT closed (age gate)
  C: STOP-ok older + negative outcome note              -> NOT closed (note gate)
  D: hard-fail STOP older than 7d                       -> alert ONCE, never closed
  E: LOOP / MOVE ON older than cutoff                   -> never closed, surfaced
  F: already-overridden STOP-ok older than cutoff       -> untouched (no rubber stamp)
  G: stale PENDING (>24h, no live lock)                 -> alert ONCE
  H: clean DB                                           -> silent, exit 0

Run:  python3 tests/test_review_queue_sweep.py
Optional: REVIEW_SWEEP_PATH=/path/to/agent-review-queue-sweep.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_env = os.environ.get("REVIEW_SWEEP_PATH")
SWEEP = Path(_env) if _env else (REPO / "ops" / "scripts" / "manage" / "agent-review-queue-sweep.py")

STOP_OK = "STOP \u2713 \u2014 goal met, quality acceptable"
STOP_FAIL = "STOP \u2717 \u2014 hard fail, escalate"
LOOP = "LOOP \U0001f504 \u2014 keep iterating"
MOVE_ON = "MOVE ON \u2192 \u2014 skip or escalate to human"
PENDING = "PENDING"

SCHEMA = """
CREATE TABLE loop_cycles (
  id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, cycle_num INTEGER,
  spec_hash TEXT, code_hash TEXT, test_output_hash TEXT, completeness REAL,
  quality REAL, progress REAL, composite REAL, no_progress INTEGER,
  decision TEXT, user_overrode INTEGER, outcome_note TEXT,
  schema_version INTEGER, model_name TEXT, session_id TEXT
);
"""


def _ts(days_ago: float) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _mkdb(rows: list[tuple]) -> tuple[str, str]:
    """Build a temp DB + isolated state dir. Row: (id, task_id, decision, days_ago, note, overrode, session)."""
    tmp = tempfile.mkdtemp(prefix="review-sweep-test-")
    db = str(Path(tmp) / "loop-governance.db")
    state = str(Path(tmp) / "state")
    os.makedirs(state, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    for rid, task_id, decision, days_ago, note, overrode, session in rows:
        con.execute(
            "INSERT INTO loop_cycles (id, timestamp, task_id, cycle_num, decision, user_overrode, outcome_note, session_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rid, _ts(days_ago), task_id, 1, decision, overrode, note, session),
        )
    con.commit()
    con.close()
    return db, state


def _run(db: str, state: str, args: list[str] | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env["REVIEW_DB_PATH"] = db
    env["REVIEW_STATE_DIR"] = state
    env["HOME"] = state
    proc = subprocess.run(
        [sys.executable, str(SWEEP)] + (args or []),
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    return proc.returncode, proc.stdout.strip()


def _row(db: str, rid: int) -> tuple:
    con = sqlite3.connect(db)
    r = con.execute(
        "SELECT decision, user_overrode, outcome_note FROM loop_cycles WHERE id=?",
        (rid,),
    ).fetchone()
    con.close()
    return r


def main() -> int:
    failures = []

    # A: STOP-ok, 10d old, clean note -> closed (accepted, note attached), silent
    db, state = _mkdb([(1, "precommit-a/init", STOP_OK, 10.0, None, None, None)])
    rc, out = _run(db, state)
    r = _row(db, 1)
    if rc != 0 or out != "" or r[1] != 0 or "auto-swept" not in (r[2] or ""):
        failures.append(f"A close: rc={rc} out={out!r} row={r!r}")

    # B: STOP-ok, 1d old -> NOT closed
    db, state = _mkdb([(2, "precommit-b/init", STOP_OK, 1.0, None, None, None)])
    _run(db, state)
    r = _row(db, 2)
    if r[1] is not None:
        failures.append(f"B age gate: row={r!r}")

    # C: STOP-ok, 10d old, negative note -> NOT closed
    db, state = _mkdb([(3, "precommit-c/init", STOP_OK, 10.0, "error during verify", None, None)])
    _run(db, state)
    r = _row(db, 3)
    if r[1] is not None:
        failures.append(f"C note gate: row={r!r}")

    # D: hard-fail, 10d old -> alert once (exit 1), never closed; second run silent
    db, state = _mkdb([(4, "precommit-d/init", STOP_FAIL, 10.0, None, None, None)])
    rc1, out1 = _run(db, state)
    r = _row(db, 4)
    rc2, out2 = _run(db, state)
    if rc1 != 1 or "hard-fail" not in out1 or r[1] is not None or rc2 != 0 or out2 != "":
        failures.append(f"D hard-fail alert+dedup: rc1={rc1} out1={out1!r} row={r!r} rc2={rc2} out2={out2!r}")

    # E: LOOP + MOVE ON, 10d old -> never closed
    db, state = _mkdb([
        (5, "precommit-e1/init", LOOP, 10.0, None, None, None),
        (6, "precommit-e2/init", MOVE_ON, 10.0, None, None, None),
    ])
    _run(db, state)
    if _row(db, 5)[1] is not None or _row(db, 6)[1] is not None:
        failures.append("E LOOP/MOVE ON never closed")

    # F: already-overridden STOP-ok, 10d old -> untouched
    db, state = _mkdb([(7, "precommit-f/init", STOP_OK, 10.0, "human note", 1, None)])
    _run(db, state)
    r = _row(db, 7)
    if r[1] != 1 or r[2] != "human note":
        failures.append(f"F override untouched: row={r!r}")

    # G: stale PENDING (>24h, no lock) -> alert once, then dedup
    db, state = _mkdb([(8, "leaky-task", PENDING, 2.0, None, None, "sess-leak01")])
    rc1, out1 = _run(db, state)
    rc2, out2 = _run(db, state)
    if rc1 != 1 or "PENDING leak" not in out1 or rc2 != 0 or out2 != "":
        failures.append(f"G pending leak+dedup: rc1={rc1} out1={out1!r} rc2={rc2} out2={out2!r}")

    # H: clean DB -> silent exit 0
    db, state = _mkdb([])
    rc, out = _run(db, state)
    if rc != 0 or out != "":
        failures.append(f"H clean silent: rc={rc} out={out!r}")

    # I: dry-run touches nothing
    db, state = _mkdb([(9, "precommit-i/init", STOP_OK, 10.0, None, None, None)])
    rc, out = _run(db, state, ["--dry-run"])
    r = _row(db, 9)
    if rc != 0 or "DRY-RUN" not in out or r[1] is not None:
        failures.append(f"I dry-run no-write: rc={rc} out={out!r} row={r!r}")

    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS — {SWEEP.name}: 9/9 scenarios (A close, B age, C note, D hard-fail, "
          "E never-close, F override, G pending-leak, H clean, I dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
