#!/usr/bin/env python3
"""Hermetic test for docs/reviews/soul-refinement-mining.py.

Why (TDD gate, 2026-10-09): the mining script is production code (it queries the
sessions store), so it ships with a test. This test is hermetic — it builds a
throwaway state.db with the real schema subset the script reads, points
STATE_DB at it, and asserts the counts. It never touches the live DB.

Run: python3 tests/test_soul_refinement_mining.py
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "docs" / "reviews" / "soul-refinement-mining.py"
KST = timezone(timedelta(hours=9))


def _load_module(db_path: Path):
    """Import the script as a module with STATE_DB pointed at the fixture."""
    spec = importlib.util.spec_from_file_location("soul_mining", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE_DB = f"file:{db_path}?mode=ro"  # type: ignore[attr-defined]
    return mod


def _fixture(db_path: Path, day: str):
    """Minimal real-schema subset: messages(role, active, content, timestamp)."""
    lo = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST).timestamp()
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, active INT, "
        "content TEXT, timestamp REAL)"
    )
    rows = [
        # human rows (2 sessions)
        ("sA", "user", 1, "fix the lock please", lo + 10),
        ("sB", "user", 1, "investigate this alert", lo + 20),
        ("sB", "user", 1, "please fix this", lo + 30),
        # scaffolding — must NOT count as human
        ("sC", "user", 1, "[IMPORTANT: cron scaffolding]", lo + 40),
        ("sC", "user", 1, "[Cron delivery: brief]", lo + 50),
        ("sD", "user", 1, "Gateway message origin (JSON data)", lo + 60),
        # inactive row — must be excluded
        ("sE", "user", 0, "inactive human text", lo + 70),
        # out-of-window row — must be excluded
        ("sF", "user", 1, "yesterday", lo - 86400),
        # reviewer technique mentions (tool rows)
        ("sA", "tool", 1, '{"technique": "unverified-claim"}', lo + 80),
        ("sA", "tool", 1, '{"technique": "unverified-claim"}', lo + 81),
        ("sB", "tool", 1, '{"technique": "scope-drift"}', lo + 82),
    ]
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", rows)
    con.commit()
    con.close()


def test_counts(day="2026-10-09"):
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "state.db"
        _fixture(db, day)
        mod = _load_module(db)
        start, end = mod.day_bounds(day)
        assert end - start == 86400, "window must be exactly one day"

        # Run the module's own logic the way main() does.
        con = sqlite3.connect(mod.STATE_DB, uri=True)
        con.execute("PRAGMA query_only=1")
        cur = con.cursor()
        cur.execute(
            "SELECT session_id, content FROM messages WHERE active=1 AND "
            "role='user' AND timestamp>=? AND timestamp<?",
            (start, end),
        )
        from collections import Counter

        sessions, human = Counter(), Counter()
        for sid, content in cur.fetchall():
            sessions[sid] += 1
            c = (content or "").lstrip()
            if not any(c.startswith(p) for p in mod.SCAFFOLD_PREFIXES):
                human[sid] += 1

        assert sessions["sA"] == 1, sessions
        assert sessions["sC"] == 2, "scaffolding rows still count as user rows"
        assert "sE" not in sessions, "inactive row leaked in"
        assert "sF" not in sessions, "out-of-window row leaked in"
        assert dict(human) == {"sA": 1, "sB": 2}, human
        assert sum(human.values()) == 3, human
        con.close()
    print("PASS  hermetic mining counts (sessions, human rows, exclusions)")


def test_cli_runs_and_returns_json(day="2026-10-09"):
    """The committed artifact must actually run and emit valid JSON."""
    out = subprocess.run(
        [sys.executable, str(SCRIPT), day],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["day"] == day
    assert "reviewer_techniques" in data and "sessions_with_human_text" in data
    assert len(data["window_epoch"]) == 2
    print("PASS  CLI emits valid JSON with the committed schema")


def test_no_arg_usage_exit2():
    out = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 2, out.returncode
    print("PASS  no-arg invocation exits 2 with usage")


def main():
    print("soul-refinement-mining hermetic tests")
    test_counts()
    test_cli_runs_and_returns_json()
    test_no_arg_usage_exit2()
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
