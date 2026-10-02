#!/usr/bin/env python3
"""Orphan-cycle resolution — honest, corroborated, and not gameable.

Luke (2026-10-02): "there should be no open cycles. if other agents started but
didn't finish, they need to be closed. what is the best way to do this?" and then
"i want you to implement 1 and 4 but ONLY if it can't be gamed. i want honesty and
doing things the right way".

Proven here, in both directions:

  A. HONESTY — an abandoned cycle is closed UNSCORED with a recomputable reason
     (tagged [orphan-reaper]), never as a judged MOVE_ON, and no score is
     invented. A live task and a cycle younger than the TTL are never touched.

  B. NOT GAMEABLE — the reaper's claim is corroborated by a contradiction that
     cannot happen honestly: a reaper-closed cycle whose OWN session still holds
     a live lock for the SAME task. The check must FAIL on exactly that, so a
     plausible-looking reason alone does not satisfy it.

  C. NO DRIFT — the writer's tag and the checker's tag must be the same string;
     a test (not a comment) enforces it.

Honest scope note: the governance DB is writable by the very session it governs,
so no marker in it is cryptographically unforgeable. What this design buys is that
a forged claim is CONTRADICTED by facts the check recomputes, and that "closed"
can never be silently read as "judged".
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# ── load the gate ──
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_orphan", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# Tests must NOT write into the PRODUCTION governance log — the gate's logger appends
# to ~/.hermes-cortex/logs/loop-governance.log, so a test run would inject fabricated
# cycles into the audit trail (found 2026-10-02 by reading the log back).
import logging as _logging  # noqa: E402

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)
_gate_log.handlers.clear()
_gate_log.propagate = False

# ── load the doctor package ──
sys.path.insert(0, str(REPO / "ops" / "scripts" / "manage"))
from cortex_doctor import checks as doc           # noqa: E402
from cortex_doctor.results import Results         # noqa: E402


def _iso(delta_s: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_s)).isoformat()


def _fresh_env(tmp: Path, cycles: list[tuple]) -> None:
    """Point the gate at a temp DB + temp lock dir, then insert cycles.

    cycles: (task_id, session_id, age_s, decision, unscored_reason, outcome_note)
    """
    tmp.mkdir(parents=True, exist_ok=True)
    setattr(mcp, "LOOP_DB", tmp / "loop-governance.db")
    setattr(mcp, "GOVERNANCE_STATE_DIR", tmp / "state")
    mcp.GOVERNANCE_STATE_DIR.mkdir(exist_ok=True)
    con = mcp._db()  # creates the real schema (init-once per process…)
    # …so a second temp DB in the same process would be empty: keep the fixture
    # self-sufficient (IF NOT EXISTS = a no-op when the gate's own DDL ran).
    con.execute(
        "CREATE TABLE IF NOT EXISTS loop_cycles ("
        " id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, cycle_num INTEGER,"
        " decision TEXT, completeness REAL, quality REAL, progress REAL, composite REAL,"
        " unscored_reason TEXT, outcome_note TEXT, session_id TEXT, user_overrode INTEGER)"
    )
    for task, sess, age, decision, reason, note in cycles:
        con.execute(
            "INSERT INTO loop_cycles (timestamp, task_id, cycle_num, decision, "
            "completeness, quality, progress, composite, "
            "unscored_reason, outcome_note, session_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_iso(age), task, 1, decision, 0.0, 0.0, 0.0, 0.0, reason, note, sess),
        )
    con.commit()
    con.close()


def _lock(tmp: Path, task: str, session: str, status: str = "in_progress") -> None:
    (tmp / "state" / f".governance-{session}.json").write_text(
        json.dumps({"task_id": task, "session_id": session, "status": status, "started_at": _iso(0)})
    )


def _row(tmp: Path, task: str) -> dict:
    con = sqlite3.connect(tmp / "loop-governance.db")
    con.row_factory = sqlite3.Row
    r = dict(con.execute("SELECT * FROM loop_cycles WHERE task_id=?", (task,)).fetchone())
    con.close()
    return r


def _status(res: Results, name: str) -> str:
    for c in res.checks:
        if c.get("name") == name:
            return str(c.get("status"))
    return "<absent>"


def _doctor_case(tmp: Path, cycle_task: str, cycle_session: str, hold_lock: bool) -> str:
    """Build a temp CORTEX_HOME holding one reaper-tagged close; return the check's status."""
    setattr(doc, "CORTEX_HOME", tmp)
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    (tmp / "state").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp / "data" / "loop-governance.db")
    con.execute(
        "CREATE TABLE IF NOT EXISTS loop_cycles (id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, "
        "session_id TEXT, decision TEXT, composite REAL, unscored_reason TEXT, outcome_note TEXT)"
    )
    con.execute(
        "INSERT INTO loop_cycles (id, timestamp, task_id, session_id, decision, composite, "
        "unscored_reason, outcome_note) VALUES (?,?,?,?,'MOVE_ON',0,?,'')",
        (9001 if hold_lock else 9002, _iso(7200), cycle_task, cycle_session,
         mcp.ORPHAN_REAPER_TAG + " abandoned: no live lock"),
    )
    con.commit()
    con.close()
    if hold_lock:
        _lock(tmp, cycle_task, cycle_session)
    res = Results()
    doc.check_orphan_cycle_resolution(res)
    return _status(res, "Orphan-cycle resolution")


def test_orphan_cycle_resolution() -> None:
    failed: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  PASS  {name}")
        else:
            failed.append(name)
            print(f"  FAIL  {name}  {detail}")

    print("A. honesty — abandoned cycles close unscored, with a recomputable reason")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _fresh_env(tmp, [("abandoned-task", "dead-session", 7200, "PENDING", None, "")])
        n = mcp._resolve_orphaned_pending_cycles()      # task_ids=None → sweep
        row = _row(tmp, "abandoned-task")
        check("reaper closed the abandoned cycle", n == 1, f"n={n}")
        check("closed (no longer PENDING)", str(row["decision"]).strip().upper() != "PENDING",
              f"decision={row['decision']!r}")
        check("NO score invented", not row["composite"], f"composite={row['composite']!r}")
        reason = str(row["unscored_reason"] or "")
        check("unscored_reason recorded and tagged",
              reason.startswith(mcp.ORPHAN_REAPER_TAG), f"reason={reason[:70]!r}")
        check("reason states recomputable facts (task + TTL)",
              "abandoned-task" in reason and "TTL" in reason, f"reason={reason[:70]!r}")

    print("A2. a LIVE task is never reaped")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _fresh_env(tmp, [("live-task", "busy-session", 7200, "PENDING", None, "")])
        _lock(tmp, "live-task", "busy-session")
        n = mcp._resolve_orphaned_pending_cycles()
        check("live task untouched", n == 0 and _row(tmp, "live-task")["decision"] == "PENDING",
              f"n={n} decision={_row(tmp, 'live-task')['decision']!r}")

    print("A3. a cycle YOUNGER than the TTL is never reaped (no racing live work)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _fresh_env(tmp, [("fresh-task", "mid-session", 5, "PENDING", None, "")])
        n = mcp._resolve_orphaned_pending_cycles()
        check("young cycle untouched", n == 0 and _row(tmp, "fresh-task")["decision"] == "PENDING",
              f"n={n}")

    print("B. corroboration — a false abandonment claim FAILS")
    with tempfile.TemporaryDirectory() as td:
        st = _doctor_case(Path(td), "faked-task", "liar-session", hold_lock=True)
        check("forged claim FAILS", st == "FAIL", f"status={st}")

    print("B2. a truthful abandonment claim does NOT fail")
    with tempfile.TemporaryDirectory() as td:
        st = _doctor_case(Path(td), "gone-task", "dead-session", hold_lock=False)
        check("truthful claim does not FAIL", st != "FAIL", f"status={st}")
        check("reaper-closed count is surfaced", st in ("PASS", "INFO"), f"status={st}")

    print("C. no drift — writer tag == checker tag")
    check("tags agree", mcp.ORPHAN_REAPER_TAG == doc.ORPHAN_REAPER_TAG,
          f"{mcp.ORPHAN_REAPER_TAG!r} vs {doc.ORPHAN_REAPER_TAG!r}")

    assert not failed, f"{len(failed)} orphan-cycle check(s) failed: {', '.join(failed)}"


if __name__ == "__main__":
    test_orphan_cycle_resolution()
    print("\n✅ all orphan-cycle resolution checks passed")
