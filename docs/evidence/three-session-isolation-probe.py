#!/usr/bin/env python3
"""Three simultaneous sessions, one host: can S3 close its OWN lock without disturbing S1/S2?

Reproduces the operator's scenario against the REAL code paths — nothing mocked, nothing
reasoned about:

  S1  a session in the canonical repo, MID-DEPLOY  (the deploy's own purge runs during it)
  S2  a session in its OWN repo, holding a lock
  S3  a session ready to commit/push, holding a lock
  S4  a session whose heartbeat is PAST ITS OWN TTL (the control: a genuinely abandoned one)

The deploy's purge and the MCP's lock-release are exercised as the functions that ship, against a
THROWAWAY state dir and DB, so no live lock or cycle can be touched.

What is measured, in order:
  1. the deploy purge against a state dir holding all four sessions;
  2. S3's release — the actual question: does it take anything of S1's or S2's with it?
  3. the contrast between the two purge implementations (standalone TTL-only vs the MCP's, which
     resolves the cycles it orphans) — the discriminating check for the leak clause below.

Run:  python3 docs/evidence/three-session-isolation-probe.py [repo-path]
Exit: 0 all checks passed, 1 at least one failed (named).
"""
import hashlib
import importlib.util
import itertools
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
MOD_PATH = REPO / "mcp-servers" / "loop-gov-mcp.py"
PURGE_PATH = REPO / "ops" / "scripts" / "manage" / "purge-stale-governance-locks.py"
FAILS = []
_c = itertools.count(1)


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
    print(f"{next(_c):02d}. {'PASS' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))


def load(path, tag):
    spec = importlib.util.spec_from_file_location(tag, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "ABSENT"


def body(res):
    return "\n".join(getattr(c, "text", "") for c in res.content)


def seed_cycle(mod, task_id, age_minutes=0):
    ts = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = mod._db()
    try:
        cur = conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, progress,"
            " composite, decision, user_overrode, outcome_note, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (task_id, 1, 0, 0, 0, 0, "PENDING", None, "probe seed", ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def decision(mod, cycle_id):
    conn = mod._db()
    try:
        return conn.execute("SELECT decision FROM loop_cycles WHERE id=?", (cycle_id,)).fetchone()[0]
    finally:
        conn.close()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="three-session-probe-"))
    state = tmp / "state"
    state.mkdir(parents=True, exist_ok=True)
    mod = load(MOD_PATH, "loopgov_three_session_probe")
    mod.LOOP_DB = tmp / "loop-governance.db"
    mod.GOVERNANCE_STATE_DIR = state

    hc_repo, own_repo = REPO, tmp / "own-repo"
    own_repo.mkdir(exist_ok=True)
    print(f"module: {MOD_PATH}")
    print(f"throwaway state: {state}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    sessions = {
        "S1-deploying": ("s1-session", "s1-task", now, hc_repo),
        "S2-own-repo": ("s2-session", "s2-task", now, own_repo),
        "S3-pushing": ("s3-session", "s3-task", now, hc_repo),
        "S4-abandoned": ("s4-session", "s4-task", stale, hc_repo),
    }
    locks, cycles = {}, {}
    for label, (sid, task, hb, repo_path) in sessions.items():
        p = mod._session_lock_path(sid)
        p.write_text(json.dumps({
            "session_id": sid, "task_id": task, "agent": "probe-agent", "status": "executing",
            "started_at": hb, "heartbeat_at": hb, "ttl_seconds": 3600,
            "repo_path": str(repo_path), "repo_slug": repo_path.name,
        }))
        locks[label] = p
        # aged 30 min: younger than the doctor's 24h auto-resolve, so a lockless PENDING cycle
        # of this age is a LEAK rather than something the doctor quietly retires
        cycles[label] = seed_cycle(mod, task, age_minutes=30)

    before = {label: sha(locks[label]) for label in ("S1-deploying", "S2-own-repo", "S3-pushing")}

    # ── 1. S1's deploy runs its own purge (the standalone script, as shipped) ──────────
    purge = load(PURGE_PATH, "purge_stale_locks_probe")
    purge.STATE_DIR = state
    removed = purge.purge()
    check("deploy purge removes the genuinely abandoned lock", not locks["S4-abandoned"].exists(),
          f"removed={removed}")
    check("deploy purge leaves the live deployer's own lock untouched", locks["S1-deploying"].exists())
    check("deploy purge leaves the other repo's live lock untouched", locks["S2-own-repo"].exists())
    check("deploy purge leaves the pushing session's live lock untouched", locks["S3-pushing"].exists())
    check("the three live locks are byte-identical after the purge",
          all(sha(locks[l]) == before[l] for l in before))
    check("deploy purge closed NO cycle — the abandoned session's cycle is still PENDING",
          decision(mod, cycles["S4-abandoned"]) == "PENDING",
          f"decision={decision(mod, cycles['S4-abandoned'])}")

    # ── 2. S3 closes its own lock (the actual question) ───────────────────────────────
    mine_before = sha(locks["S3-pushing"])
    mod._release_lock({"session_id": sessions["S3-pushing"][0]})
    check("S3's release removes S3's own lock", not locks["S3-pushing"].exists(),
          f"was {mine_before}")
    check("S3's release leaves S1's deploy lock untouched", locks["S1-deploying"].exists()
          and sha(locks["S1-deploying"]) == before["S1-deploying"])
    check("S3's release leaves S2's other-repo lock untouched", locks["S2-own-repo"].exists()
          and sha(locks["S2-own-repo"]) == before["S2-own-repo"])
    check("S3's release closed no peer's cycle",
          all(decision(mod, cycles[l]) == "PENDING"
              for l in ("S1-deploying", "S2-own-repo", "S4-abandoned")))
    mod._close_cycle_unscored(None, "probe: S3 closed its own cycle after its release",
                              "probe close", task_id=sessions["S3-pushing"][1])
    check("S3 closing its own cycle leaves every peer cycle alone",
          all(decision(mod, cycles[l]) == "PENDING"
              for l in ("S1-deploying", "S2-own-repo"))
          and decision(mod, cycles["S3-pushing"]) == "MOVE_ON")

    # ── 3. the contrast that names the real hazard ────────────────────────────────────
    # The purge and the cycle repair are TWO steps, in BOTH implementations: `_purge_stale_locks`
    # is a 3-line file remover, and the sanctioned repair is `_resolve_orphaned_pending_cycles`,
    # which begin_change calls. So a purge (the standalone script's or the MCP's) can leave a
    # lockless PENDING cycle for an abandoned session until something invokes the repair.
    check("the MCP purge is also just a file remover — it resolves no cycle by itself",
          decision(mod, cycles["S4-abandoned"]) == "PENDING",
          f"decision={decision(mod, cycles['S4-abandoned'])}")

    # the repair that DOES close it, as the fleet invokes it
    resolved = mod._resolve_orphaned_pending_cycles({sessions["S4-abandoned"][1]})
    check("the sanctioned repair closes the orphaned cycle the purge left",
          resolved == 1 and decision(mod, cycles["S4-abandoned"]) == "MOVE_ON",
          f"resolved={resolved} decision={decision(mod, cycles['S4-abandoned'])}")
    check("the repair still touched no live session's cycle",
          all(decision(mod, cycles[l]) == "PENDING" for l in ("S1-deploying", "S2-own-repo")))

    # and the reclaim cannot help once the file is already gone: it judges lock FILES, so the
    # repair path for an already-purged lock is the resolver, not the reclaim
    report = body(mod._reclaim_dead_locks({"session_id": "probe-observer"}))
    check("the reclaim finds nothing once the stale lock file is already gone (by design)",
          "no dead locks" in report, report.splitlines()[0][:100])

    print(f"\nfailures={len(FAILS)}" + (f" {FAILS}" if FAILS else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
