"""Hermetic regression test: multiple concurrent sessions writing to the
loop-governance DB must queue on the busy lock, not fail with
'database is locked'.

Repro (2026-09-29, luke / concurrent hermes-cortex sessions on moses):
every interactive Hermes session spawns its OWN loop-gov-mcp.py daemon,
and each daemon opens its own connection to the shared
~/.hermes-cortex/data/loop-governance.db. When two sessions call
begin_change() at the same time, the second write hit
'database is locked' and could never acquire its governance lock —
locking the whole repo to one session even though the lock FILES are
session-scoped (pre-commit-score line 642 documents that intent).

Root cause: _db() opened connections with `sqlite3.connect(str(LOOP_DB))`
= default 5s busy timeout. Under real contention that is not enough for a
concurrent writer to finish, and there was no explicit busy_timeout /
WAL setup, so the second writer errored instead of queuing.

Fix under test: _db() must (a) open every connection with a generous
busy timeout, (b) enable WAL journal mode so readers never block writers,
so two simultaneous writers serialize and BOTH succeed.

Regression coverage:
  A. _db() connection has a busy_timeout >= 30s and journal_mode = WAL
  B. two concurrent writers to the same DB both succeed (second queues,
     does not error with 'database is locked')

Run:  python3 tests/test_loop_gov_multi_session.py
"""
import importlib.util
import os
import tempfile
import threading
import time
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

_FAIL = []


def _reset(home: Path):
    """Repoint the module's DB at a fresh temp sandbox."""
    mcp.LOOP_DB = home / "loop.db"
    mcp.CONFIG_PATH = home / "config.json"
    mcp.CACHE_DB = home / "cache.db"
    mcp.GOVERNANCE_STATE_DIR = home / "state"
    mcp.FORCE_AUDIT_PATH = mcp.GOVERNANCE_STATE_DIR / "force-acquire-audit.json"
    mcp.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp._require_dogfood = lambda: None


def _insert_from_connection(conn, task_id: str) -> str:
    """One INSERT+commit on a caller-supplied connection; returns err or ''."""
    try:
        conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, "
            "progress, composite, no_progress, decision, user_overrode, session_id) "
            "VALUES (?,1,0,0,0,0,0,'PENDING',NULL,?)",
            (task_id, "sess-" + task_id),
        )
        conn.commit()
        return ""
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return str(e)


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="gov-multi-session-test-"))
    _reset(home)

    # ── A: connection carries a busy timeout + WAL ──
    conn = mcp._db()
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    if busy < 30000:
        _FAIL.append(f"A: busy_timeout={busy}, expected >= 30000ms")
    if journal.lower() != "wal":
        _FAIL.append(f"A: journal_mode={journal!r}, expected 'wal'")

    # ── B: two concurrent writers both succeed (second must queue, not error) ──
    results = {}

    def writer(tid: str):
        conn = mcp._db()
        try:
            results[tid] = _insert_from_connection(conn, tid)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Writer A takes the write lock first and holds it for ~1s (a plausible
    # concurrent begin_change). Writer B starts right behind.
    marker = threading.Event()

    def _writer_a():
        conn = mcp._db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            marker.set()
            time.sleep(1.0)
            conn.execute(
                "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, "
                "progress, composite, no_progress, decision, user_overrode, session_id) "
                "VALUES ('writer-a',1,0,0,0,0,0,'PENDING',NULL,'sess-a')"
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    ta = threading.Thread(target=_writer_a)
    tb = threading.Thread(target=writer, args=("writer-b",))
    ta.start()
    if not marker.wait(timeout=5):
        _FAIL.append("B: writer A never acquired the write lock")
    tb.start()
    tb.join(timeout=60)
    ta.join(timeout=60)

    if results.get("writer-b"):
        _FAIL.append(f"B: concurrent writer errored: {results['writer-b']}")

    # Verify both rows actually landed.
    c = mcp._db()
    try:
        count = c.execute(
            "SELECT COUNT(*) FROM loop_cycles WHERE task_id IN ('writer-a','writer-b')"
        ).fetchone()[0]
    finally:
        c.close()
    if count != 2:
        _FAIL.append(f"B: expected 2 rows, got {count}")

    if _FAIL:
        print(f"FAIL ({len(_FAIL)}):")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("PASS — loop-gov multi-session DB: A(busy_timeout+WAL) B(concurrent writers both succeed) green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
