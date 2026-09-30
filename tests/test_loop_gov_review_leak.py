"""Regression test: _record_review must not leak its DB connection (or its
write-lock) on the duplicate-review path.

Incident class (2026-09-30, root cause of "review agents can't close out"):
every end_change retry on a complex change re-runs the adversarial reviewer and
re-INSERTs into adversarial_reviews.cycle_id, which is UNIQUE. The old code did:

    try:
        conn = _db()
        conn.execute("INSERT INTO adversarial_reviews ...")
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        pass                 # <-- conn never closed

On the duplicate (IntegrityError) path the connection was left OPEN, and in WAL
mode that leaked its write transaction into the long-lived serving daemon — the
DB stayed write-locked until the daemon was killed, so every review retry wedged
begin_change/feedback for all sessions and forced pointless daemon kills.

The fix closes the connection on EVERY path via try/finally. This test pins that
contract: after a duplicate review (IntegrityError), the DB must remain fully
writable — no leaked write-lock.

Hermetic: temp GOVERNANCE_STATE_DIR + LOOP_DB, never the real DB.
Run:  <venv-python> tests/test_loop_gov_review_leak.py
"""

import importlib.util
import os
import sqlite3
import tempfile
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
        f"lgm_rev_{os.urandom(4).hex()}", _MCP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.GOVERNANCE_STATE_DIR = Path(state_dir)
    mod.LOOP_DB = Path(loop_db)
    return mod


def _db_writable(db_path, timeout_ms=2000):
    """True if we can acquire a BEGIN IMMEDIATE write lock within timeout_ms."""
    conn = sqlite3.connect(str(db_path), timeout=timeout_ms / 1000.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=%d" % int(timeout_ms))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        return True
    except sqlite3.OperationalError as e:
        return False if "locked" in str(e).lower() else True
    finally:
        conn.close()


def main():
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        db = Path(td) / "loop-governance.db"
        mod = _load_module(state, db)

        # ---- 1. baseline: DB writable before any review
        check("DB writable before any review", _db_writable(db))

        # ---- 2. seed a cycle so _record_review has a cycle_id
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS loop_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                task_id TEXT NOT NULL, cycle_num INTEGER NOT NULL,
                spec_hash TEXT, code_hash TEXT, test_output_hash TEXT,
                completeness REAL NOT NULL, quality REAL NOT NULL,
                progress REAL NOT NULL, composite REAL NOT NULL,
                no_progress INTEGER NOT NULL DEFAULT 0,
                decision TEXT NOT NULL, user_overrode INTEGER,
                outcome_note TEXT, schema_version INTEGER DEFAULT 1,
                model_name TEXT, session_id TEXT, unscored_reason TEXT)
        """)
        conn.execute(
            "INSERT INTO loop_cycles (task_id, cycle_num, completeness, quality,"
            " progress, composite, decision) VALUES (?,?,?,?,?,?,?)",
            ("t", 1, 10.0, 10.0, 10.0, 10.0, "STOP"))
        conn.commit()
        cycle_id = conn.execute("SELECT MAX(id) FROM loop_cycles").fetchone()[0]
        conn.close()

        # ---- 3. first _record_review: fresh INSERT, succeeds
        mod._record_review(cycle_id, "r1", "m", "CLEAN", "[]", "first")
        check("DB writable after FIRST review (fresh insert)", _db_writable(db))

        # ---- 4. DUPLICATE _record_review: same cycle_id -> UNIQUE conflict ->
        #         IntegrityError path. THIS is where the leak used to be.
        mod._record_review(cycle_id, "r2", "m", "FINDINGS", "[x]", "duplicate")
        check("DB writable after DUPLICATE review (IntegrityError path, no leak)",
              _db_writable(db))

        # ---- 5. adversarial_reviews has exactly ONE row (idempotent no-op)
        conn = sqlite3.connect(str(db))
        n = conn.execute("SELECT COUNT(*) FROM adversarial_reviews").fetchone()[0]
        conn.close()
        check("duplicate review is idempotent (1 row)", n == 1, f"got {n}")

        # ---- 6. the leaked connection's write reservation is NOT held: confirm
        #         no open connection count grew (all conns from _record_review
        #         were closed). We can't count fds hermetic-ly across module, but
        #         writability after BOTH calls is the load-bearing assertion.
        check("DB still writable after all review calls", _db_writable(db))

    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {_FAIL}")
        return 1
    print("ALL PASS — no connection leak on the duplicate-review path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())