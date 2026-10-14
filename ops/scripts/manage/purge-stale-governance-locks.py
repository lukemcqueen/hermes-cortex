#!/usr/bin/env python3
"""
Purge stale governance lock files from crashed sessions.

Scans ~/.hermes-cortex/state/ for .governance-*.json files whose
heartbeat has exceeded their TTL and removes them. Also cleans
orphan symlinks pointing to deleted targets.

Designed as a no_agent cron (silent when clean, reports only
when locks were removed).

2026-10-14, TWO GUARDS in front of every removal (this script used to be TTL-only, which made it
the odd one out against the fleet's staleness rule):

  1. LIVENESS — a stale LOOKING lock is not a dead session. A long stretch of editing and
     committing makes no governed call, so the heartbeat freezes while the agent is plainly busy.
     `_agent_worked_since` mirrors the MCP's rescue; without it this sweep removes a BUSY session's
     lock and its next write is refused — the deadlock the MCP-side rescue was added to remove.

  2. NO LOCKLESS PENDING CYCLE (#125) — a lock file is removed only after its task's PENDING cycle
     is resolved UNSCORED. Otherwise an abandoned session's row (younger than the doctor's 24h
     auto-resolve window) becomes a LEAK that FAILs the host and blocks every agent's push, with no
     owner left to clear it. If the cycle cannot be confirmed resolved the lock is KEPT — fail
     closed: a stale lock is harmless, a lockless PENDING cycle is not.

FIXED 2026-07-31: the main block (count = purge(), output, exit) was
inadvertently indented inside the def, so the script only defined the
function and exited 0 — the purge cron was a silent no-op. The loop
also referenced an undefined `marker` variable (NameError) in what was
meant to be a separate 24h marker cleanup. Both are corrected here.
"""

import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# CORTEX_HOME-driven (matching agent-pending-cycle-watchdog.py) so the whole sweep can be pointed at
# a throwaway tree by a test or a probe. Unset in the deploy and the cron: the paths are unchanged.
CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".hermes-cortex")))
STATE_DIR = CORTEX_HOME / "state"
DB_PATH = CORTEX_HOME / "data" / "loop-governance.db"
DEFAULT_TTL = 3600  # 1 hour
MARKER_MAX_AGE = 86400  # 24 hours


def _is_lock_stale(state: dict, mtime_fallback: float | None = None) -> bool:
    """Check if a lock's heartbeat has exceeded its TTL.

    2026-09-17 (Titus LEAK report): time-only heartbeats ("09:12:00Z") and
    naive (no-tz) heartbeats defeat datetime.fromisoformat / aware-vs-naive
    subtraction — the old code caught both and returned False, pinning the
    lock and its orphaned PENDING cycle forever (doctor FAIL, push blocked).
    Fix: fall back to the lock file's mtime when the heartbeat can't be aged
    in-band, and treat naive timestamps as UTC.
    """
    ttl = state.get("ttl_seconds", DEFAULT_TTL)
    heartbeat_str = state.get("heartbeat_at", state.get("started_at", ""))
    now = datetime.now(timezone.utc)
    if heartbeat_str:
        try:
            hb_str = heartbeat_str.replace("Z", "+00:00")
            heartbeat = datetime.fromisoformat(hb_str)
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            return (now - heartbeat).total_seconds() > ttl
        except (ValueError, TypeError):
            pass
    if mtime_fallback is not None:
        return (now.timestamp() - mtime_fallback) > ttl
    return False


def _agent_worked_since(state: dict) -> bool:
    """Did the lock's own agent author a commit in the lock's own repo since its heartbeat?

    A stale-looking lock is not a dead session: a long stretch of editing and committing makes no
    governed tool call, so the heartbeat freezes while the agent is plainly busy. This mirrors the
    MCP's `_session_worked_since` — the fleet's staleness rule has had this rescue since 2026-10-13,
    but this standalone script kept a TTL-ONLY copy, so the deploy's purge (and the cron that runs
    this file) would still remove a BUSY session's lock: the next write from that session is refused
    and the exact deadlock the rescue exists to remove comes back. A parity test
    (tests/test_purge_resolves_orphaned_cycles.py) pins the two implementations against drifting.

    Never raises: a failure here must not decide a lock's fate. (False = no evidence of work, which
    leaves the TTL decision standing.)
    """
    try:
        repo = state.get("repo_path")
        heartbeat = state.get("heartbeat_at", state.get("started_at", ""))
        author = (state.get("agent") or "").strip()
        if not repo or not heartbeat or author in ("", "unknown"):
            return False
        if not Path(repo).is_dir():
            return False
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--since=" + heartbeat, "--author=" + author,
             "--format=%H", "-n", "1"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        return bool(out)
    except Exception:
        return False


def _close_pending_cycle(task_id: str) -> bool:
    """Resolve a task's PENDING cycle UNSCORED before its lock is removed. True when it is resolved.

    #125 (2026-10-14). Removing a lock FILE resolves no cycle, so an abandoned session's still
    PENDING row — younger than the doctor's 24h auto-resolve window — becomes a LEAK: the host then
    FAILs the PENDING-cycles check and blocks EVERY agent's push, with no owner left to clear it.
    Measured in docs/evidence/three-session-isolation-probe.py.

    Returns False when the row cannot be confirmed resolved — the caller must then KEEP the lock.
    That is the fail-closed direction on purpose: a stale lock left on disk is harmless (the next
    sweep retries it), while a lockless PENDING cycle blocks the whole host.

    MOVE_ON with the facts in unscored_reason/outcome_note, matching the MCP's shared closer
    (`_close_cycle_unscored`) so an auditor recomputes the same story from either path.
    """
    if not DB_PATH.exists():
        print(f"cannot resolve cycles: no governance store at {DB_PATH}", file=sys.stderr)
        return False
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            "UPDATE loop_cycles SET decision='MOVE_ON', unscored_reason=?, outcome_note=? "
            "WHERE task_id=? AND decision='PENDING' AND user_overrode IS NULL",
            ("lock purged as stale by the TTL sweep — nothing was closed or reviewed",
             "stale lock purged — nothing reviewed (no receipt)", task_id),
        )
        conn.commit()
        left = conn.execute(
            "SELECT COUNT(*) FROM loop_cycles WHERE task_id=? AND decision='PENDING'",
            (task_id,)).fetchone()[0]
        return left == 0
    except sqlite3.Error as e:
        print(f"could not resolve the PENDING cycle for {task_id}: {e}", file=sys.stderr)
        return False
    finally:
        if conn is not None:
            conn.close()


@dataclass
class SweepResult:
    """What a sweep did, INCLUDING what it deliberately did not do.

    A bare count cannot express the two outcomes that need an operator (2026-10-14 review): locks
    kept because their cycle could not be resolved, and lock files too corrupt to age at all. Both
    are invisible in "removed=0", and silence on a broken store is how a repairable state becomes a
    permanent one.
    """
    removed: int = 0
    kept_busy: int = 0          # kept: the lock's agent has committed since (a busy session)
    kept_unresolved: int = 0    # kept: its PENDING cycle could not be resolved (fail closed)
    corrupt: list = field(default_factory=list)   # unparseable AND older than 2x TTL


def sweep() -> SweepResult:
    """One sweep: remove what is provably dead, keep what cannot be safely removed."""
    result = SweepResult()
    if not STATE_DIR.exists():
        return result

    # Phase 1: Remove stale real files
    # P1-A: NEVER delete unparseable files — an unparseable lock is a lock
    # being written right now (non-atomic write). Deleting it steals another
    # session's fresh lock. Only parseable-and-stale locks are removed.
    # …but an unparseable file whose mtime is well past the TTL is not a race any more, it is a
    # corrupted artifact: it can never be aged, so it and any cycle behind it sit forever. Those
    # are COLLECTED for the operator (a distinct, loud outcome) rather than silently skipped
    # forever (2026-10-14 review, finding 7).
    for lock_file in sorted(STATE_DIR.glob(".governance-*.json")):
        try:
            if lock_file.is_symlink():
                continue  # Process real file separately
            state = json.loads(lock_file.read_text())
            try:
                mtime = lock_file.stat().st_mtime
            except OSError:
                mtime = None
            if _is_lock_stale(state, mtime):
                # (1) A stale-LOOKING lock is not a dead session — see _agent_worked_since.
                if _agent_worked_since(state):
                    result.kept_busy += 1
                    continue
                # (2) Never remove the lock of a task whose PENDING cycle cannot be resolved
                # (#125): the removal is what turns an abandoned session into a leak that blocks
                # every push on this host. Fail closed — keep the lock, retry next sweep.
                task_id = (state.get("task_id") or "").strip()
                if task_id and not _close_pending_cycle(task_id):
                    result.kept_unresolved += 1
                    continue
                lock_file.unlink()
                result.removed += 1
        except (json.JSONDecodeError, OSError, ValueError):
            try:
                age = datetime.now().timestamp() - lock_file.stat().st_mtime
            except OSError:
                age = 0
            if age > 2 * DEFAULT_TTL:
                result.corrupt.append(f"{lock_file.name} (unparseable, untouched for "
                                      f"{int(age / 3600)}h)")
            else:
                print(f"skipping unparseable lock file (mid-write?): {lock_file.name}",
                      file=sys.stderr)
        try:
            if lock_file.is_symlink() and not lock_file.exists():
                lock_file.unlink()
                result.removed += 1
        except OSError:
            print("expected — silently handled", file=sys.stderr)

    # Phase 2: Remove stale session marker files (.hermes-session-*.id) older than 24h.
    # NOTE: previously inlined in the lock loop with an undefined `marker`
    # variable, which crashed the loop. Moved to its own loop here.
    for marker in sorted(STATE_DIR.glob(".hermes-session-*.id")):
        try:
            mtime = os.path.getmtime(marker)
            age = (datetime.now().timestamp() - mtime)
            if age > MARKER_MAX_AGE:  # 24 hours
                marker.unlink()
                result.removed += 1
        except OSError:
            print("expected — silently handled", file=sys.stderr)

    return result


def purge() -> int:
    """Backwards-compatible count-only view of one sweep. Returns count removed."""
    return sweep().removed


def main() -> int:
    """Entrypoint. Silent when clean — a no_agent cron with empty stdout delivers nothing.

    Exit 2 when the sweep could not do its job for a reason a human must act on (an unresolvable
    store, or lock files too corrupt to age). A cron that only ever exits 0 turns a broken
    governance store into background noise, which is exactly how a repairable host becomes a
    permanent one.
    """
    result = sweep()
    if result.removed:
        print(f"🧹 Purged {result.removed} stale governance lock file(s)")
    if result.kept_busy:
        print(f"⏳ Kept {result.kept_busy} stale-looking lock(s): their agents have committed since "
              f"the heartbeat — busy sessions, not dead ones")
    if result.corrupt:
        print("⚠️ CORRUPT governance lock file(s) — unparseable and untouched for more than "
              "2x TTL, so they can never be aged and any cycle behind them is stuck. "
              "OPERATOR ACTION: inspect and remove, then re-run the doctor:")
        for item in result.corrupt:
            print(f"     {item}")
    if result.kept_unresolved:
        print(f"❌ Kept {result.kept_unresolved} stale lock(s) whose PENDING cycles could not be "
              f"resolved — the governance store is unreadable or unwritable. Removing them would "
              f"leave lockless PENDING cycles, which fail the doctor for EVERY agent on this host. "
              f"OPERATOR ACTION: repair the store, then re-run this sweep.")
        return 2
    return 2 if result.corrupt else 0


if __name__ == "__main__":
    # NEVER at module level (fixed 2026-10-14): `count = purge()` + `sys.exit(0)` used to run on
    # IMPORT, so any tool that imported this module to exercise its shipped logic — a test, a
    # probe, a doctor check — purged the LIVE state directory as a side effect of loading it, and
    # the importer could not prevent it (repointing STATE_DIR after the import is too late).
    # Observed for real: a probe importing this file removed 780 abandoned lock files before it
    # could repoint anything. Import must be inert; only running the file has effects.
    sys.exit(main())
