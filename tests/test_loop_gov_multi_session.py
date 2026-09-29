"""Hermetic regression test: multiple concurrent sessions writing to the
loop-governance DB must queue on the busy lock, not fail with
'database is locked'.

Repro (2026-09-29, luke / concurrent hermes-cortex sessions on moses):
every interactive Hermes session spawns its OWN loop-gov-mcp.py daemon
(= its own OS process), and each process opens its own connection to the
shared ~/.hermes-cortex/data/loop-governance.db. When two sessions call
begin_change() at the same time, the second write hit
'database is locked' and could never acquire its governance lock —
locking the whole repo to one session even though the lock FILES are
session-scoped (pre-commit-score line 642 documents that intent).

Root cause: _db() opened connections with `sqlite3.connect(str(LOOP_DB))`
= default 5s busy timeout, and no explicit WAL/busy_timeout pragma. Under
real contention (a peer holding the write lock), the second writer gave up
and errored instead of queuing.

Fix under test: _db() opens with timeout=30, forces PRAGMA journal_mode=WAL,
and sets PRAGMA busy_timeout=30000 so concurrent writers serialize cleanly,
and VERIFIES the resulting journal mode rather than silently swallowing a
failed pragma (adversarial finding ADV-0-3).

Regression coverage (adversarial-verifier feedback ADV-0-1/2/3):
  A. _db() connection carries busy_timeout >= 30000ms and journal_mode = wal
     (read back from the connection's actual PRAGMA returns, not assumed)
  B. two concurrent OS PROCESSES (multiprocessing — faithful to the
     separate-daemon failure the bug manifests through) both write to the
     same DB while one holds the lock 8s; with the 30s busy timeout the
     second queues and succeeds.
  C. CONTROL: an equivalent connection opened with the OLD default 5s busy
     timeout is subjected to the same 8s write-lock hold and MUST fail with
     'database is locked' — proving the old timeout was genuinely
     insufficient and the 30s fix is what makes B pass.

Run:  python3 tests/test_loop_gov_multi_session.py
"""
import importlib.util
import multiprocessing
import sqlite3
import tempfile
import time
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

_FAIL = []
HOLD_S = 8.0  # > old 5s busy_timeout, < new 30s — beats old, fits new


def _reset(home: Path):
    """Repoint the module's DB at a fresh temp sandbox."""
    mcp.LOOP_DB = home / "loop.db"
    mcp.CONFIG_PATH = home / "config.json"
    mcp.CACHE_DB = home / "cache.db"
    mcp.GOVERNANCE_STATE_DIR = home / "state"
    mcp.FORCE_AUDIT_PATH = mcp.GOVERNANCE_STATE_DIR / "force-acquire-audit.json"
    mcp.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp._require_dogfood = lambda: None


def _setup_db(path: str) -> None:
    """Create the schema once so worker processes only INSERT (no ALTER race)."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS loop_cycles ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " task_id TEXT NOT NULL, cycle_num INTEGER NOT NULL,"
        " completeness REAL NOT NULL, quality REAL NOT NULL,"
        " progress REAL NOT NULL, composite REAL NOT NULL,"
        " no_progress INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL,"
        " user_overrode INTEGER, outcome_note TEXT, session_id TEXT)"
    )
    conn.commit()
    conn.close()


def _insert(conn, task_id: str) -> str:
    """One INSERT+commit; returns '' on success or the error string."""
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


# ── Worker processes (each is its own OS process + own connection) ──


def _worker_hold(path: str, task_id: str, hold_s: float, q) -> None:
    """Take the write lock, hold it hold_s seconds, then commit one row."""
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("BEGIN IMMEDIATE")
    time.sleep(hold_s)
    conn.execute(
        "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality, "
        "progress, composite, no_progress, decision, user_overrode, session_id) "
        f"VALUES ('{task_id}',1,0,0,0,0,0,'PENDING',NULL,'sess-{task_id}')"
    )
    conn.commit()
    conn.close()
    q.put(("held", task_id, "ok"))


def _worker_busy(path: str, task_id: str, timeout_s: float, q) -> None:
    """Open a connection with the given busy timeout and try a write while
    another process holds the lock; report the attempt's error/time."""
    conn = sqlite3.connect(path, timeout=timeout_s)
    start = time.time()
    res = _insert(conn, task_id)
    elapsed = round(time.time() - start, 2)
    conn.close()
    q.put(("busy", task_id, res, elapsed))


def main() -> int:
    ctx = multiprocessing.get_context("fork")
    home = Path(tempfile.mkdtemp(prefix="gov-multi-session-test-"))
    _reset(home)
    db = str(mcp.LOOP_DB)
    _setup_db(db)

    # ── A: connection carries busy_timeout + WAL (verified, ADV-0-3) ──
    conn = mcp._db()
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    if busy < 30000:
        _FAIL.append(f"A: busy_timeout={busy}, expected >= 30000ms")
    if str(journal).lower() != "wal":
        _FAIL.append(f"A: journal_mode={journal!r}, expected 'wal'")

    # ── B: two concurrent PROCESSES; second succeeds under 30s fix ──
    qb = ctx.Queue()
    hold_p = ctx.Process(target=_worker_hold, args=(db, "held-b", HOLD_S, qb))
    busy_p = ctx.Process(target=_worker_busy, args=(db, "writer-b", 30.0, qb))
    hold_p.start()
    time.sleep(0.3)  # ensure holder acquires write lock before busy writer starts
    busy_p.start()
    hold_p.join(timeout=40)
    busy_p.join(timeout=120)
    if busy_p.is_alive():
        busy_p.terminate()
        _FAIL.append("B: busy writer never returned (timed out)")
    if hold_p.is_alive():
        hold_p.terminate()
    results_b = {}
    while not qb.empty():
        tag, tid, *rest = qb.get()
        results_b[tid] = rest

    # ── C: CONTROL — old 5s default, same hold, MUST fail with 'locked' ──
    qc = ctx.Queue()
    hold_c = ctx.Process(target=_worker_hold, args=(db, "held-c", HOLD_S, qc))
    busy_c = ctx.Process(target=_worker_busy, args=(db, "writer-c", 5.0, qc))
    hold_c.start()
    time.sleep(0.3)
    busy_c.start()
    hold_c.join(timeout=40)
    busy_c.join(timeout=120)
    if busy_c.is_alive():
        busy_c.terminate()
    if hold_c.is_alive():
        hold_c.terminate()
    results_c = {}
    while not qc.empty():
        tag, tid, *rest = qc.get()
        results_c[tid] = rest

    # ── Assertions ──
    # B: writer-b succeeded under the fix.
    if results_b.get("writer-b", ["(no result)", None])[0]:
        _FAIL.append(f"B: concurrent writer errored: {results_b['writer-b']}")
    # C: writer-c FAILED under the old 5s timeout with the SAME hold.
    c_res = results_c.get("writer-c", ["(no result)", None])
    c_err = c_res[0]
    if "database is locked" not in str(c_err).lower():
        _FAIL.append(
            "C: control did NOT reproduce old failure — expected 'database is "
            f"locked' with 5s timeout vs {HOLD_S}s hold, got: {c_err!r}"
        )

    # Verify writer-b's row actually landed in the DB.
    c = mcp._db()
    try:
        landed = c.execute(
            "SELECT COUNT(*) FROM loop_cycles WHERE task_id='writer-b'"
        ).fetchone()[0]
    finally:
        c.close()
    if landed != 1:
        _FAIL.append(f"B: writer-b's row did not land (count={landed})")

    if _FAIL:
        print(f"FAIL ({len(_FAIL)}):")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    b_elapsed = results_b["writer-b"][1]
    print("PASS — loop-gov multi-session DB (adversarial findings resolved):")
    print(f"  A: _db() busy_timeout={busy}ms, journal_mode={journal} (verified)")
    print(f"  B: 2 concurrent OS processes both write while lock held {HOLD_S}s "
          f"(writer-b queued {b_elapsed}s, no error)")
    print(f"  C: control with OLD 5s timeout FAILED under same hold — "
          f"proves fix required: {results_c['writer-c'][0]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
