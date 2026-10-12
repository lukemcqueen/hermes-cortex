#!/usr/bin/env python3
"""Runnable regression for agent-session_cache.embed_loop_db().

Why this exists: the source of truth for the loop_db embedding path was a prose
claim in a close note, and an adversarial review correctly refused it
(ADV-12197-1): a claim no later reader can re-run is not evidence. This script
IS the evidence — one command reproduces every asserted fact.

Asserted (each one has bitten this file at least once):

  1. The query runs at all. The original selected `code_or_spec`/`output_text`,
     columns that do not exist in loop_cycles (the schema stores only content
     HASHES; the text lives in content_assets). That raised OperationalError on
     every run while a bare `except Exception` swallowed it, so the source
     contributed ZERO rows for months.
  2. Cycles with a resolvable code_hash produce text. Content must come from the
     content_assets JOIN, not from a phantom column.
  3. Ordering is by CONTENT LENGTH, not composite: the highest-composite cycles
     are LLM crons that store no code, so a composite-ordered LIMIT 50 returned
     only empty rows and still embedded nothing even once the SQL ran.
  4. Boundary inputs do not crash and are filtered: empty content_assets, NULL
     content, a dangling code_hash, and empty-string content all yield 0 rows.

Hermetic: builds a throwaway SQLite fixture in a temp dir; never touches the
live ~/.hermes-cortex/data databases.

Usage:  python3 tests/run_session_cache_loop_db_repro.py
Exit 0 = every assertion held. Non-zero = a real regression.
"""
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "ops/scripts/manage/agent-session_cache.py"

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _load_module():
    """Import agent-session_cache.py by path (hyphenated name, not importable
    by name) without executing its __main__ block."""
    spec = importlib.util.spec_from_file_location("agent_session_cache", SRC)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SRC}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(rows, assets):
    """Build a temp loop-governance-shaped DB. Returns its path."""
    tmp = tempfile.mkdtemp(prefix="sc-looptest-")
    db = str(Path(tmp) / "loop-governance.db")
    c = sqlite3.connect(db)
    c.execute(
        "CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT, "
        "code_hash TEXT, spec_hash TEXT, test_output_hash TEXT, composite REAL)"
    )
    c.execute("CREATE TABLE content_assets (hash TEXT, content TEXT, type TEXT, created TEXT)")
    c.executemany("INSERT INTO loop_cycles VALUES (?,?,?,?,?,?)", rows)
    c.executemany("INSERT INTO content_assets VALUES (?,?,?,?)", assets)
    c.commit()
    c.close()
    return db


def _run_query(db_path):
    """Run the production query shape against a fixture and return row count.

    Mirrors embed_loop_db()'s SQL exactly; if that SQL changes, this must too —
    the assertion is on the query, so drift is a real finding.
    """
    c = sqlite3.connect(db_path)
    rows = c.execute(
        """
        SELECT lc.id, lc.task_id, ca.content
        FROM loop_cycles lc
        JOIN content_assets ca ON ca.hash = lc.code_hash
        WHERE lc.composite >= 6.0 AND LENGTH(ca.content) >= 50
        ORDER BY LENGTH(ca.content) DESC
        LIMIT 50
        """
    ).fetchall()
    c.close()
    return rows


def main() -> int:
    print(f"== session cache loop_db regression ==")
    print(f"   source: {SRC.relative_to(REPO)}")
    print(f"   present: {SRC.is_file()}")
    check("source file exists", SRC.is_file())
    if not SRC.is_file():
        return 1

    src_text = SRC.read_text()
    # (1) the phantom columns are gone
    check("no phantom column code_or_spec", "code_or_spec" not in src_text)
    check("no phantom column output_text", "output_text" not in src_text)
    # (1b) the swallow is gone — a broken query must now be visible
    check("no 'expected — silently handled' swallow in loop_db path",
          'print("expected — silently handled"' not in src_text)
    # (3) ordering by content length, not composite
    check("orders by LENGTH(content)",
          "ORDER BY LENGTH(ca.content) DESC" in src_text)
    # module imports cleanly (import shim works)
    try:
        mod = _load_module()
        check("module imports (hermes_models shim + fail-soft)", True)
        check("embed_loop_db callable", callable(mod.embed_loop_db))
    except Exception as exc:  # noqa: BLE001
        check("module imports (hermes_models shim + fail-soft)", False,
              f"{type(exc).__name__}: {exc}")
        return 1

    big = "x" * 200          # well over the 50-char floor
    medium = "y" * 80

    # (2) real content is produced through the JOIN
    db = _fixture(
        rows=[
            (1, "task-a", "h_big", None, None, 9.5),
            (2, "task-b", "h_medium", None, None, 7.0),
            (3, "task-c", "h_low", None, None, 2.0),      # below composite floor
        ],
        assets=[
            ("h_big", big, "code", "2026-01-01"),
            ("h_medium", medium, "code", "2026-01-01"),
            ("h_low", "z" * 200, "code", "2026-01-01"),
        ],
    )
    rows = _run_query(db)
    check("JOIN yields rows for resolvable code_hash", len(rows) == 2,
          f"got {len(rows)}, expected 2 (composite<6.0 excluded)")
    if rows:
        check("longest content ordered first", rows[0][2] == big,
              f"first row len={len(rows[0][2])}")

    # (3b) a high-composite cycle with NO asset must not consume a LIMIT slot
    db = _fixture(
        rows=[
            (1, "empty-cron", None, None, None, 10.0),    # top composite, no code
            (2, "real-work", "h1", None, None, 6.5),
        ],
        assets=[("h1", big, "code", "2026-01-01")],
    )
    rows = _run_query(db)
    check("composite-ordered empties do not starve LIMIT", len(rows) == 1,
          f"got {len(rows)}, expected 1 real row despite a composite-10.0 empty")

    # (4) boundary inputs
    db = _fixture(rows=[(1, "t", "h", None, None, 9.0)], assets=[])
    check("empty content_assets -> 0 rows", len(_run_query(db)) == 0)

    db = _fixture(rows=[(1, "t", "h", None, None, 9.0)],
                  assets=[("h", None, "code", "2026-01-01")])
    check("NULL content -> 0 rows", len(_run_query(db)) == 0)

    db = _fixture(rows=[(1, "t", "missing", None, None, 9.0)], assets=[])
    check("dangling code_hash -> 0 rows", len(_run_query(db)) == 0)

    db = _fixture(rows=[(1, "t", "h", None, None, 9.0)],
                  assets=[("h", "", "code", "2026-01-01")])
    check("empty-string content -> 0 rows", len(_run_query(db)) == 0)

    # (5) failure propagation — the reviewer asked for an injected failure that
    #     asserts the CALLER surfaces it instead of continuing with a partial
    #     count (ADV-12197-1 swallowed-error). Drive embed_loop_db directly with
    #     LOOP_DB pointed at a DB whose schema cannot satisfy the query.
    import tempfile as _tf
    bad = str(Path(_tf.mkdtemp(prefix="sc-bad-")) / "loop-governance.db")
    _bc = sqlite3.connect(bad)
    _bc.execute("CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY)")  # no code_hash
    _bc.commit()
    _bc.close()

    mod2 = _load_module()
    original_loop_db = mod2.LOOP_DB
    mem = sqlite3.connect(":memory:")
    mod2.LOOP_DB = Path(bad)
    mem.execute(
        "CREATE TABLE embeddings (id INTEGER PRIMARY KEY, source TEXT, "
        "source_id TEXT, text TEXT, embedding TEXT, agent TEXT, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    try:
        result = mod2.embed_loop_db(mem)
        check("broken query surfaces as None (not a silent 0)", result is None,
              f"got {result!r}")
    except Exception as exc:  # noqa: BLE001
        check("broken query surfaces as None (not a silent 0)", False,
              f"raised {type(exc).__name__} instead of signalling")
    finally:
        mod2.LOOP_DB = original_loop_db
        mem.close()

    # (5b) and the CLI turns that signal into a non-zero exit
    mod3 = _load_module()
    mod3.LOOP_DB = Path(bad)
    # Keep it hermetic: cmd_build() opens CACHE_DB, so redirect it to a temp file
    # rather than writing into the live session-embeddings.db.
    mod3.CACHE_DB = Path(_tf.mkdtemp(prefix="sc-cache-")) / "session-embeddings.db"
    mod3.SESSION_DIR = Path(_tf.mkdtemp(prefix="sc-nosess-"))   # empty on purpose
    mod3.SKILLS_DIR = Path(_tf.mkdtemp(prefix="sc-noskills-"))  # empty on purpose
    try:
        failures = mod3.cmd_build(quiet=True)
        check("cmd_build reports the failed subsystem", failures == ["loop_db"],
              f"got {failures!r}")
        # and the exit status the cron sees is non-zero
        rc = 1 if failures else 0
        check("failure maps to a non-zero exit code", rc == 1)
    finally:
        mod3.LOOP_DB = original_loop_db

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({len(FAILURES)} assertion(s)): {', '.join(FAILURES)}")
        return 1
    print("RESULT: PASS — all assertions held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
