#!/usr/bin/env python3
"""Drive reclaim_dead_locks against a THROWAWAY state dir + DB, end to end.

Every path is repointed away from live state (LOOP_DB, GOVERNANCE_STATE_DIR) before anything
runs, so this cannot touch the host's real locks or its governance store.

Three locks are planted and the tool is asked to judge them:
  * DEAD   — a peer's lock with a heartbeat two hours past its 3600s TTL and no commits by that
             agent in that repo, plus a PENDING cycle;
  * FRESH  — a peer's lock with a current heartbeat (a live owner), plus a PENDING cycle;
  * OWN    — this session's own lock, also with a PENDING cycle (own locks are skipped outright).

REPORT mode must list exactly the dead one and change nothing; APPLY mode must remove the dead
lock file and close only its cycle UNSCORED, leaving the fresh and own locks and their cycles
untouched.

Run:  python3 docs/evidence/reclaim-dead-locks-probe.py [repo-path]
Exit: 0 all checks passed, 1 at least one failed (named).
"""
import importlib.util
import itertools
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
MOD = REPO / "mcp-servers" / "loop-gov-mcp.py"
FAILS = []
_c = itertools.count(1)


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
    print(f"{next(_c):02d}. {'PASS' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))


def body(res):
    return "\n".join(getattr(c, "text", "") for c in res.content)


def load():
    spec = importlib.util.spec_from_file_location("loopgov_reclaim_under_test", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed_cycle(mod, task_id):
    conn = mod._db()
    try:
        cur = conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, progress,"
            " composite, decision, user_overrode, outcome_note) VALUES (?,?,?,?,?,?,?,?,?)",
            (task_id, 1, 0, 0, 0, 0, "PENDING", None, "probe seed"),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def cycle_row(mod, cycle_id):
    conn = mod._db()
    try:
        return conn.execute(
            "SELECT decision, unscored_reason FROM loop_cycles WHERE id=?", (cycle_id,)).fetchone()
    finally:
        conn.close()


def write_lock(mod, sid, task, heartbeat, tmp, agent):
    p = mod._session_lock_path(sid)
    p.write_text(json.dumps({
        "session_id": sid, "task_id": task, "agent": agent, "status": "executing",
        "started_at": heartbeat, "heartbeat_at": heartbeat, "ttl_seconds": 3600,
        "repo_path": str(tmp), "repo_slug": "probe-repo",
    }))
    return p


def main():
    tmp = Path(tempfile.mkdtemp(prefix="reclaim-probe-"))
    mod = load()
    mod.LOOP_DB = tmp / "loop-governance.db"
    mod.GOVERNANCE_STATE_DIR = tmp / "state"
    mod.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"module: {MOD}")
    print(f"throwaway state: {tmp}")

    old = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    own_sid = "probe-own-session"

    dead_lock = write_lock(mod, "probe-dead", "probe-dead-task", old, tmp, "probe-agent")
    fresh_lock = write_lock(mod, "probe-live", "probe-live-task", now, tmp, "probe-agent")
    own_lock = write_lock(mod, own_sid, "probe-own-task", old, tmp, "probe-agent")
    dead_cycle = seed_cycle(mod, "probe-dead-task")
    live_cycle = seed_cycle(mod, "probe-live-task")
    own_cycle = seed_cycle(mod, "probe-own-task")
    args = {"session_id": own_sid}

    # ── report mode: names the dead lock, changes nothing ─────────────────────────────
    report = body(mod._reclaim_dead_locks(args))
    check("report names the dead lock", "probe-dead-task" in report)
    check("report does NOT name the live owner's lock", "probe-live-task" not in report)
    check("report does NOT name this session's own lock", "probe-own-task" not in report)
    check("report says it changed nothing", "REPORT ONLY" in report)
    check("report removed no lock file",
          dead_lock.exists() and fresh_lock.exists() and own_lock.exists())
    check("report closed no cycle", cycle_row(mod, dead_cycle)["decision"] == "PENDING")

    # ── apply mode: ends the dead lock, closes only its cycle ─────────────────────────
    applied = body(mod._reclaim_dead_locks({**args, "apply": True}))
    check("apply reports one dead lock ended", "ended 1 dead lock" in applied)
    check("apply removed the dead lock file", not dead_lock.exists())
    check("apply left the live owner's lock alone", fresh_lock.exists())
    check("apply left this session's own lock alone", own_lock.exists())
    row = cycle_row(mod, dead_cycle)
    check("apply closed the dead task's cycle UNSCORED",
          row["decision"] == "MOVE_ON" and bool(row["unscored_reason"]),
          f"decision={row['decision']}")
    check("apply invented no score",
          cycle_row(mod, dead_cycle)["unscored_reason"] is not None)
    check("apply left the live owner's cycle PENDING",
          cycle_row(mod, live_cycle)["decision"] == "PENDING")
    check("apply left this session's own cycle PENDING",
          cycle_row(mod, own_cycle)["decision"] == "PENDING")
    check("apply does not inherit the dead session's scope",
          "never inherits their scope" in applied)

    # ── idempotence: a second report finds nothing left ───────────────────────────────
    again = body(mod._reclaim_dead_locks(args))
    check("second report finds no dead locks", "no dead locks" in again)

    print(f"\nfailures={len(FAILS)}" + (f" {FAILS}" if FAILS else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
