#!/usr/bin/env python3
"""The legacy-reaper backfill must clear the doctor's INFO without inventing a verdict.

The doctor's `Orphan-cycle resolution` check reports cycles closed by the OLD orphan
reaper (bare MOVE_ON, empty `unscored_reason`) so they are never read as judged. That
report can only be cleared by TAGGING those rows — the distinction the check protects
has to be made, not asserted. These tests drive the detector with controlled inputs in
both directions: the legacy row must be tagged, and the already-tagged / genuinely
scored rows must be left alone.

Run: python3 -m pytest tests/test_backfill_legacy_reaper_cycles.py -q
"""

import importlib.util
import sqlite3
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "ops" / "scripts" / "manage" / "backfill-legacy-reaper-cycles.py"
_DOCTOR_CHECKS = _REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py"
_MCP = _REPO / "mcp-servers" / "loop-gov-mcp.py"

_LEGACY_NOTE = "auto-resolved by governance MCP - task has no live lock (abandoned/crashed session)"


def _load():
    spec = importlib.util.spec_from_file_location("backfill_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_db(tmp_path) -> Path:
    db = tmp_path / "loop-governance.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT, session_id TEXT, "
        "decision TEXT, outcome_note TEXT, unscored_reason TEXT)"
    )
    con.executemany(
        "INSERT INTO loop_cycles (id, task_id, session_id, decision, outcome_note, unscored_reason) VALUES (?,?,?,?,?,?)",
        [
            # the case the doctor reports: old reaper, bare MOVE_ON, no reason
            (901, "old-abandoned-task", "cron_x_1", "MOVE_ON", _LEGACY_NOTE, None),
            # already tagged by the CURRENT reaper — must be left byte-identical
            (902, "already-tagged", "cron_x_2", "MOVE_ON", _LEGACY_NOTE,
             "[orphan-reaper] abandoned: no live lock for task 'already-tagged'"),
            # a genuinely judged cycle that merely has no unscored_reason
            (903, "scored-task", "sess_3", "MOVE_ON", "verified: 42 tests pass, rc=0", None),
        ],
    )
    con.commit()
    con.close()
    return db


def _reason(db: Path, cid: int):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("SELECT unscored_reason FROM loop_cycles WHERE id=?", (cid,)).fetchone()[0]
    finally:
        con.close()


def test_dry_run_writes_nothing(tmp_path):
    db = _fake_db(tmp_path)
    rc = _load().run(db, apply=False, out=lambda *a, **k: None)
    assert rc == 0, rc
    assert _reason(db, 901) is None, "dry run must not write"
    print("  dry run leaves the legacy row untagged ✓")


def test_apply_tags_only_the_legacy_row(tmp_path):
    db = _fake_db(tmp_path)
    mod = _load()
    rc = mod.run(db, apply=True, out=lambda *a, **k: None)
    assert rc == 0, rc
    tagged = _reason(db, 901)
    assert tagged.startswith(mod.ORPHAN_REAPER_TAG), tagged
    assert "legacy" in tagged, tagged
    assert _reason(db, 902) == "[orphan-reaper] abandoned: no live lock for task 'already-tagged'", \
        "an already-tagged row must not be rewritten"
    assert _reason(db, 903) is None, "a scored cycle must not be given an unscored_reason"
    print("  apply tags the legacy row and leaves the others alone ✓")


def test_apply_is_idempotent(tmp_path):
    db = _fake_db(tmp_path)
    mod = _load()
    assert mod.run(db, apply=True, out=lambda *a, **k: None) == 0
    lines = []
    rc = mod.run(db, apply=True, out=lines.append)
    assert rc == 0, rc
    assert "nothing to do" in "\n".join(lines), lines
    assert len(mod.legacy_rows(sqlite3.connect(db))) == 0
    print("  a second --apply finds nothing to do ✓")


def test_the_doctor_predicate_then_finds_nothing(tmp_path):
    """The point of the tool: the doctor's OWN legacy query must return zero rows."""
    db = _fake_db(tmp_path)
    mod = _load()
    mod.run(db, apply=True, out=lambda *a, **k: None)
    con = sqlite3.connect(db)
    try:
        n = len(mod.legacy_rows(con))
        tagged = con.execute(
            "SELECT count(*) FROM loop_cycles WHERE unscored_reason LIKE ?", (mod.ORPHAN_REAPER_TAG + "%",)
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 0, n
    assert tagged == 2, tagged  # the old row is now visible to the reaper set too
    print("  the doctor's legacy query returns zero rows after the backfill ✓")


def test_a_missing_db_is_a_could_not_verify(tmp_path):
    lines = []
    rc = _load().run(tmp_path / "nope.db", apply=True, out=lines.append)
    assert rc == 3, rc
    assert "COULD NOT VERIFY" in "\n".join(lines), lines
    print("  a missing DB returns exit 3, not a silent pass ✓")


def test_the_tag_matches_the_doctor_and_the_mcp_server():
    """One tag, three readers. A drift here silently splits the reaped set from the report."""
    mod = _load()
    assert f'ORPHAN_REAPER_TAG = "{mod.ORPHAN_REAPER_TAG}"' in _DOCTOR_CHECKS.read_text(), "doctor tag drift"
    assert f'ORPHAN_REAPER_TAG = "{mod.ORPHAN_REAPER_TAG}"' in _MCP.read_text(), "mcp-server tag drift"
    print("  ORPHAN_REAPER_TAG agrees across the backfill, the doctor and the MCP server ✓")


if __name__ == "__main__":
    import sys

    sys.exit(__import__("pytest").main([__file__, "-q"]))
