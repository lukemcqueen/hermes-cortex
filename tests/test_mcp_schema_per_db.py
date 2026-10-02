#!/usr/bin/env python3
"""The loop-governance MCP schema guard must be keyed by DATABASE, not by process.

`_ensure_schema` cached a single process-global boolean, so the FIRST database a
process opened got `loop_cycles` and every LATER one was skipped — the guard
returned early and the caller then queried a table that was never created:

    sqlite3.OperationalError: no such table: loop_cycles

Production opens exactly one DB per process, so it never noticed. The repo's own
sandbox tests repoint `LOOP_DB` to a temp file, so they hit it — 5 tests in
tests/test_runtime/test_mcp_closeout.py failed in a FULL-SUITE run and passed in
isolation (2026-10-02), which is the signature of order-dependent global state.

Run: python3 -m pytest tests/test_mcp_schema_per_db.py -q -s
"""
import importlib.util
import sqlite3
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_schema", _MCP_PATH)
assert _spec and _spec.loader, f"cannot load {_MCP_PATH}"
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)


def _has_loop_cycles(path: Path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='loop_cycles'"
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def test_schema_is_created_in_every_database_the_process_opens(tmp_path, monkeypatch):
    """The second database this process opens must get its own schema."""
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"

    monkeypatch.setattr(mcp, "LOOP_DB", first)
    conn = mcp._db()
    conn.close()
    assert _has_loop_cycles(first), "the first database never got the schema"

    # Repointed to a different file — the guard must not treat it as done.
    monkeypatch.setattr(mcp, "LOOP_DB", second)
    conn = mcp._db()
    try:
        conn.execute("SELECT count(*) FROM loop_cycles").fetchone()
    finally:
        conn.close()
    assert _has_loop_cycles(second), (
        "the second database opened in the same process has no loop_cycles table — "
        "the schema guard is process-global instead of per-database")


def test_the_guard_is_the_process_global_it_replaced(tmp_path, monkeypatch):
    """Premise: this test is only meaningful while _ensure_schema is the guard.

    If the DDL moves elsewhere (or the guard is deleted), re-derive the test
    rather than trusting a green run here.
    """
    assert hasattr(mcp, "_ensure_schema"), "loop-gov-mcp no longer has _ensure_schema"
    source = _MCP_PATH.read_text()
    assert "_ensure_schema(conn)" in source, "the DDL entry point moved — re-derive this test"
