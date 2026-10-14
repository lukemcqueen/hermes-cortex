#!/usr/bin/env python3
"""Drive the release-first paths against a THROWAWAY state dir and tmp DB.

Every path is repointed away from live state (LOOP_DB, GOVERNANCE_STATE_DIR) before
anything runs, so this cannot touch the host's governance store or its locks.

Twelve checks, on the REAL module imported from the repo under test:
  1-3. _close_cycle_unscored resolves a live PENDING row unscored, records the reason,
       and invents no score;
  4-5. it never rewrites a row that is already scored or overridden;
  6-7. an UPDATE that raises is REPORTED (not raised) and the connection is still closed;
  8-10. _release_after_refusal closes the cycle AND removes the lock, and says so;
  11-12. a lock carrying no session_id releases nothing and leaves its cycle PENDING.

Run:  python3 docs/evidence/release-closes-cycle-probe.py [repo-path]
Exit: 0 all checks passed, 1 at least one failed (the failures are named).
"""
import importlib.util
import itertools
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
MOD = REPO / "mcp-servers" / "loop-gov-mcp.py"
FAILS = []
_c = itertools.count(1)


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name)
    print(f"{next(_c):02d}. {tag} {name}" + (f" — {detail}" if detail else ""))


def load():
    spec = importlib.util.spec_from_file_location("loopgov_under_test", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed(mod, task_id, decision="PENDING", overrode=None):
    conn = mod._db()
    try:
        cur = conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, progress,"
            " composite, decision, user_overrode, outcome_note) VALUES (?,?,?,?,?,?,?,?,?)",
            (task_id, 1, 0, 0, 0, 0, decision, overrode, "seed"),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def row(mod, cycle_id):
    conn = mod._db()
    try:
        return conn.execute(
            "SELECT decision, unscored_reason, outcome_note FROM loop_cycles WHERE id=?",
            (cycle_id,)).fetchone()
    finally:
        conn.close()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="release-probe-"))
    mod = load()
    mod.LOOP_DB = tmp / "loop-governance.db"
    mod.GOVERNANCE_STATE_DIR = tmp / "state"
    mod.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"module: {MOD}")
    print(f"throwaway state: {tmp}")

    cid = seed(mod, "probe-a")
    ok = mod._close_cycle_unscored(cid, "probe reason", "probe outcome (no receipt)")
    r = row(mod, cid)
    check("closes a PENDING row unscored", ok and r["decision"] == "MOVE_ON",
          f"decision={r['decision']}")
    check("records the reason an auditor can recompute", r["unscored_reason"] == "probe reason")
    check("invents no score", r["outcome_note"] == "probe outcome (no receipt)")

    scored = seed(mod, "probe-b", decision="STOP")
    overrode = seed(mod, "probe-c", decision="PENDING", overrode=1)
    check("leaves a scored row alone",
          mod._close_cycle_unscored(scored, "x", "y") is False
          and row(mod, scored)["decision"] == "STOP")
    check("leaves an overridden row alone",
          mod._close_cycle_unscored(overrode, "x", "y") is False
          and row(mod, overrode)["decision"] == "PENDING")

    real_db = mod._db
    closed = []

    class Boom:
        def execute(self, *a, **k):
            raise sqlite3.OperationalError("probe: store gone")

        def close(self):
            closed.append(True)

    mod._db = lambda: Boom()
    try:
        ok = mod._close_cycle_unscored(cid + 1000, "x", "y")
    finally:
        mod._db = real_db
    check("reports failure instead of raising", ok is False)
    check("closes the connection on the failure path (no leak)", closed == [True],
          f"close() calls={len(closed)}")

    cid4 = seed(mod, "probe-d")
    sid = "probe-session-4"
    lockp = mod._session_lock_path(sid)
    lockp.write_text(json.dumps({"session_id": sid, "task_id": "probe-d", "status": "executing"}))
    note = mod._release_after_refusal({"session_id": sid, "task_id": "probe-d"}, cid4)
    check("findings refusal removed the lock", not lockp.exists())
    check("findings refusal closed the cycle unscored",
          row(mod, cid4)["decision"] == "MOVE_ON", f"decision={row(mod, cid4)['decision']}")
    check("findings refusal says the lock is released", "RELEASED" in note)

    cid5 = seed(mod, "probe-e")
    note5 = mod._release_after_refusal({"task_id": "probe-e"}, cid5)
    check("nameless lock is not released", "NOT released" in note5)
    check("nameless lock leaves its cycle PENDING", row(mod, cid5)["decision"] == "PENDING")

    print(f"\nfailures={len(FAILS)}" + (f" {FAILS}" if FAILS else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
