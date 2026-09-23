"""The close-out gate must test the SCORE, not the spelling of the decision.

Audit finding (2026-09-23, Luke Q: "How are you able to pass without
scoring?"): `_end_change` treated a cycle as scored when `user_overrode` was
set, and skipped the block for any decision that was not *exactly* the string
"LOOP" — so "LOOP 🔄 — keep iterating" walked straight through, and
`feedback_accept` could close a cycle with composite 0.0 and nothing measured.

New rule (approved 2026-09-23):
  * decision comparison is by CLASS (prefix), not exact equality;
  * a cycle is closed out only when composite > 0 OR an explicit
    `unscored_reason` is recorded — an unscored close must say why.
"""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"


@pytest.fixture()
def mcp(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("loop_gov_gate", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "LOOP_DB", tmp_path / "loop-governance.db")
    monkeypatch.setattr(mod, "get_session_id", lambda args: "sess_gate")
    monkeypatch.setattr(mod, "_read_lock", lambda args: {
        "task_id": args.get("task_id", ""), "session_id": "sess_gate"})
    return mod


def _cycle(mod, task_id, decision="PENDING", composite=0.0,
           completeness=0.0, quality=0.0, progress=0.0,
           overrode=None, unscored_reason=None):
    conn = mod._db()
    conn.execute(
        "INSERT INTO loop_cycles (task_id, cycle_num, session_id, completeness, quality, "
        "progress, composite, decision, user_overrode, unscored_reason) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (task_id, 0, "sess_gate", completeness, quality, progress, composite,
         decision, overrode, unscored_reason))
    conn.commit()
    conn.execute("DELETE FROM loop_cycles WHERE id <> (SELECT MAX(id) FROM loop_cycles)")
    conn.commit()
    conn.close()


def _row(mod):
    conn = mod._db()
    row = conn.execute("SELECT * FROM loop_cycles ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row)


def _text(result):
    return result.content[0].text


# ── 1. decision classes ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("LOOP 🔄 — keep iterating", "LOOP"),
    ("MOVE ON → proceed", "MOVE_ON"),
    ("MOVE_ON", "MOVE_ON"),
    ("STOP ✗ — hard fail, escalate", "STOP"),
    ("STOP ✓ — verified", "STOP"),
    ("PENDING", "PENDING"),
    (None, "PENDING"),
    ("", "PENDING"),
])
def test_decision_class_buckets_decorated_labels(mcp, raw, expected):
    assert mcp._decision_class(raw) == expected


# ── 2. accept requires a score or a stated reason ──────────────────────

def test_accept_without_score_or_reason_is_refused(mcp):
    _cycle(mcp, "gate-a")

    out = _text(mcp._feedback_accept({"task_id": "gate-a", "note": "looks done"}))

    assert "unscored" in out.lower()
    assert "unscored_reason" in out          # remedy must be named
    assert "completeness" in out             # both options offered
    assert _row(mcp)["decision"] == "PENDING"


def test_accept_with_unscored_reason_closes_and_records_it(mcp):
    _cycle(mcp, "gate-b")

    out = _text(mcp._feedback_accept({
        "task_id": "gate-b", "note": "audit only",
        "unscored_reason": "read-only audit — no diff to measure"}))

    row = _row(mcp)
    assert row["decision"] == "MOVE_ON"
    assert row["unscored_reason"] == "read-only audit — no diff to measure"
    assert "unscored_reason" not in out or "accepted" in out.lower()


def test_accept_with_scores_needs_no_reason(mcp):
    _cycle(mcp, "gate-c")

    _text(mcp._feedback_accept({
        "task_id": "gate-c", "note": "verified",
        "completeness": 10, "quality": 9, "progress": 8}))

    row = _row(mcp)
    assert row["composite"] > 0.0
    assert row["unscored_reason"] is None


# ── 3. end_change enforces the same rule ───────────────────────────────

def test_end_change_blocks_decorated_loop_cycle_without_score(mcp):
    """The bug: 'LOOP 🔄 — keep iterating' != 'LOOP', so the guard skipped."""
    _cycle(mcp, "gate-d", decision="LOOP 🔄 — keep iterating",
           composite=0.0, overrode=0)

    out = _text(mcp._end_change({"task_id": "gate-d"}))

    assert "NOT scored" in out or "not scored" in out
    assert "Cannot release lock" in out


def test_end_change_blocks_unscored_accept_without_reason(mcp):
    _cycle(mcp, "gate-e", decision="MOVE_ON", composite=0.0, overrode=0)

    out = _text(mcp._end_change({"task_id": "gate-e"}))

    assert "Cannot release lock" in out
    assert "unscored_reason" in out


def test_end_change_passes_with_a_real_score(mcp):
    _cycle(mcp, "gate-f", decision="MOVE_ON", composite=8.2,
           completeness=10, quality=8, progress=6, overrode=0)

    out = _text(mcp._end_change({"task_id": "gate-f"}))

    assert "Cannot release lock" not in out


def test_end_change_passes_with_explicit_unscored_reason(mcp):
    _cycle(mcp, "gate-g", decision="MOVE_ON", composite=0.0, overrode=0,
           unscored_reason="audit only — nothing to measure")

    out = _text(mcp._end_change({"task_id": "gate-g"}))

    assert "Cannot release lock" not in out


def test_end_change_still_blocks_a_pending_cycle(mcp):
    _cycle(mcp, "gate-h", decision="PENDING", composite=0.0)

    out = _text(mcp._end_change({"task_id": "gate-h"}))

    assert "Cannot release lock" in out


# ── 5. begin_change close-out gate uses the class too ──────────────────

def test_begin_change_refuses_on_decorated_pending_cycle(mcp):
    """'PENDING — mid-work' is still PENDING; the old exact match missed it."""
    _cycle(mcp, "gate-i", decision="PENDING — mid-work", composite=0.0)

    out = _text(mcp._begin_change({"task_id": "gate-j", "description": "next"}))

    assert "Close out your previous task" in out


def test_begin_change_allows_when_prior_cycle_is_closed_out(mcp):
    _cycle(mcp, "gate-k", decision="MOVE_ON → proceed", composite=8.0,
           completeness=10, quality=8, progress=6, overrode=0)

    out = _text(mcp._begin_change({"task_id": "gate-l", "description": "next"}))

    assert "Close out your previous task" not in out


def test_unscored_reason_column_is_added_to_a_legacy_db(mcp, tmp_path):
    legacy = tmp_path / "legacy.db"
    import sqlite3
    conn = sqlite3.connect(str(legacy))
    conn.execute("CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT, "
                 "decision TEXT, composite REAL, user_overrode INTEGER)")
    conn.commit()
    conn.close()

    mcp.LOOP_DB = legacy
    conn = mcp._db()                      # must migrate, not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loop_cycles)")}
    conn.close()
    assert "unscored_reason" in cols

    conn = mcp._db()                      # second call: still fine
    conn.close()
