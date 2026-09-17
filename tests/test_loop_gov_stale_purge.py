"""Hermetic regression test: stale-governance-lock purge must age out
time-only/naive heartbeats and resolve the orphaned PENDING cycles.

Repro (2026-09-17, Titus / luke@macOS): live lock files in
~/.hermes-cortex/state/, some of them orphans whose owning processes were
gone. Lock 163455 carried a time-only heartbeat (e.g. "09:12:00Z") —
datetime.fromisoformat raises ValueError on it, the old _is_lock_stale
caught it and returned False ("never stale"), so the lock was never purged
and its PENDING cycle stayed leaked -> doctor FAILed every push.

Regression coverage:
  A. _is_lock_stale: time-only heartbeat + old file mtime  -> stale
  B. _is_lock_stale: naive (no-tz) stale heartbeat          -> stale
  C. _is_lock_stale: fresh heartbeat (any format)           -> not stale
  D. _purge_stale_locks: purges a stale time-only lock AND resolves the
     orphaned PENDING cycle for that task (decision -> MOVE_ON)
  E. _resolve_orphaned_pending_cycles(None): locksless PENDING older than TTL
     is resolved; a PENDING with a live lock is left alone.

Run:  python3 tests/test_loop_gov_stale_purge.py
"""
import importlib.util
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

_FAIL = []


def _reset(home: Path):
    """Repoint the module's DB + state dir at a fresh temp sandbox."""
    mcp.LOOP_DB = home / "loop.db"
    mcp.CONFIG_PATH = home / "config.json"
    mcp.CACHE_DB = home / "cache.db"
    mcp.GOVERNANCE_STATE_DIR = home / "state"
    mcp.FORCE_AUDIT_PATH = mcp.GOVERNANCE_STATE_DIR / "force-acquire-audit.json"
    mcp.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp._require_dogfood = lambda: None


def _stale_state(heartbeat: str, mtime_age_s=7200):
    """Lock state with an old mtime (to fall back on for time-only hb)."""
    now = datetime.now(timezone.utc)
    started = (now - timedelta(days=2)).isoformat()
    return {
        "task_id": "stale-task",
        "status": "executing",
        "heartbeat_at": heartbeat,
        "started_at": started,
        "ttl_seconds": 3600,
    }, mtime_age_s


def _mkdb(home: Path, rows):
    conn = mcp._db()
    for tid, decision, age_h, session in rows:
        ts = (datetime.now(timezone.utc) - timedelta(hours=age_h)).isoformat()
        conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, progress, "
            "composite, no_progress, decision, user_overrode, timestamp, session_id) "
            "VALUES (?,1,0,0,0,0,0,?,NULL,?,?)",
            (tid, decision, ts, session),
        )
    conn.commit()
    conn.close()


def _decision(task_id: str) -> str:
    conn = mcp._db()
    row = conn.execute(
        "SELECT decision FROM loop_cycles WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else "MISSING"


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="gov-stale-purge-test-"))
    _reset(home)
    sdir = mcp.GOVERNANCE_STATE_DIR

    # A+B: time-only and naive stale heartbeats -> stale (via mtime fallback)
    for label, hb in [("time-only", "09:12:00Z"), ("naive", "2026-09-17T08:00:00")]:
        st, age = _stale_state(hb)
        if not mcp._is_lock_stale(st, time.time() - age):
            _FAIL.append(f"A/B {label}: stale heartbeat not aged stale")

    # time-only with a FRESH mtime -> not stale (P1-A: don't purge a live write)
    st, _ = _stale_state("09:12:00Z")
    if mcp._is_lock_stale(st, time.time() - 10):
        _FAIL.append("A: time-only heartbeat with fresh mtime falsely stale")

    # C: fresh heartbeat -> not stale
    st2, _ = _stale_state(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    if mcp._is_lock_stale(st2, time.time() - 5):
        _FAIL.append("C: fresh heartbeat judged stale")

    # D: write a stale time-only lock + orphan PENDING cycle for its task;
    #    purge must remove the lock AND resolve the cycle.
    old_mtime = time.time() - 7200
    lock = {"task_id": "snapshot-capture-chunked-commit", "status": "executing",
            "heartbeat_at": "09:12:00Z",  # time-only — the 163455 shape
            "started_at": "2026-09-17T00:12:00Z", "ttl_seconds": 3600}
    lf = sdir / ".governance-stale-timeonly.json"
    lf.write_text(json.dumps(lock))
    os.utime(lf, (old_mtime, old_mtime))
    _mkdb(home, [("snapshot-capture-chunked-commit", "PENDING", 30, "sess-dead1")])
    removed = mcp._purge_stale_locks()
    if removed != 1:
        _FAIL.append(f"D: purge removed {removed} locks, expected 1")
    if lf.exists():
        _FAIL.append("D: stale time-only lock not removed")
    if _decision("snapshot-capture-chunked-commit") != "MOVE_ON":
        _FAIL.append(f"D: orphan PENDING cycle not resolved, got {_decision('snapshot-capture-chunked-commit')}")

    # E: sweep-all — locksless PENDING older than TTL resolved; live-lock PENDING kept
    _mkdb(home, [("orphan-no-lock", "PENDING", 30, "sess-dead2"),
                 ("current-live", "PENDING", 1, "sess-live1")])
    live_lock = {"task_id": "current-live", "status": "executing",
                 "heartbeat_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                 "started_at": datetime.now(timezone.utc).isoformat(), "ttl_seconds": 3600}
    (sdir / ".governance-live1.json").write_text(json.dumps(live_lock))
    mcp._resolve_orphaned_pending_cycles()
    if _decision("orphan-no-lock") != "MOVE_ON":
        _FAIL.append(f"E: lockless orphan not resolved: {_decision('orphan-no-lock')}")
    if _decision("current-live") != "PENDING":
        _FAIL.append(f"E: live-lock PENDING wrongly resolved: {_decision('current-live')}")

    if _FAIL:
        print(f"FAIL ({len(_FAIL)}):")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("PASS — loop-gov stale purge: A(time-only) B(naive) C(fresh) D(purge+resolve) E(sweep-all) all green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())