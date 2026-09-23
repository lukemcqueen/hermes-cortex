"""feedback_accept must be able to record a real score — and must not invent one.

Regression (2026-09-23 audit): every cycle closed through feedback_accept kept
composite 0.0 while the pre-commit path recorded 7.8-8.1, so trend queries read
"accepted" as "failed". The fix lets the caller supply completeness / quality /
progress (0-10); composite is recomputed from the same configured weights the
scoring path uses, and a cycle closed without scores stays unscored.
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"


@pytest.fixture()
def mcp(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("loop_gov_scores", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "LOOP_DB", tmp_path / "loop-governance.db")
    monkeypatch.setattr(mod, "get_session_id", lambda args: "sess_scores")
    return mod


def _pending_cycle(mod, task_id="score-test"):
    conn = mod._db()
    conn.execute(
        "INSERT INTO loop_cycles (task_id, cycle_num, session_id, completeness, quality, "
        "progress, composite, decision) VALUES (?,?,?,?,?,?,?,?)",
        (task_id, 0, "sess_scores", 0.0, 0.0, 0.0, 0.0, "PENDING"))
    conn.commit()
    cycle_id = conn.execute(
        "SELECT id FROM loop_cycles ORDER BY id DESC LIMIT 1").fetchone()["id"]
    conn.close()
    return cycle_id


def _row(mod, cycle_id):
    conn = mod._db()
    row = conn.execute("SELECT * FROM loop_cycles WHERE id = ?", (cycle_id,)).fetchone()
    conn.close()
    return dict(row)


def _text(result):
    return result.content[0].text


def test_scores_are_recorded_and_composite_uses_configured_weights(mcp):
    cycle_id = _pending_cycle(mcp)
    weights = mcp._config()["weights"]

    out = _text(mcp._feedback_accept({
        "cycle_id": cycle_id, "note": "verified",
        "completeness": 10, "quality": 8, "progress": 6,
    }))

    row = _row(mcp, cycle_id)
    assert row["completeness"] == 10.0
    assert row["quality"] == 8.0
    assert row["progress"] == 6.0
    expected = round(
        10 * weights["completeness"] + 8 * weights["quality"] + 6 * weights["progress"], 2)
    assert row["composite"] == expected > 0.0
    assert row["decision"] == "MOVE_ON"
    assert str(expected) in out


def test_no_scores_needs_a_stated_reason(mcp):
    """Was: closes unscored. Now: an unscored close must say WHY (2026-09-23)."""
    cycle_id = _pending_cycle(mcp, "score-test-none")

    refused = _text(mcp._feedback_accept({"cycle_id": cycle_id, "note": "audit only"}))
    assert "Refusing to close" in refused
    assert _row(mcp, cycle_id)["decision"] == "PENDING"

    out = _text(mcp._feedback_accept({
        "cycle_id": cycle_id, "note": "audit only",
        "unscored_reason": "read-only audit — no diff to measure"}))

    row = _row(mcp, cycle_id)
    assert row["composite"] == 0.0          # unchanged — never fabricated
    assert row["decision"] == "MOVE_ON"
    assert "read-only audit" in out


def test_out_of_range_score_is_refused_and_cycle_untouched(mcp):
    cycle_id = _pending_cycle(mcp, "score-test-bad")

    out = _text(mcp._feedback_accept({"cycle_id": cycle_id, "quality": 42}))

    assert "between 0 and 10" in out
    assert _row(mcp, cycle_id)["decision"] == "PENDING"


def test_non_numeric_score_is_refused(mcp):
    cycle_id = _pending_cycle(mcp, "score-test-type")

    out = _text(mcp._feedback_accept({"cycle_id": cycle_id, "completeness": "great"}))

    assert "must be a number" in out
    assert _row(mcp, cycle_id)["decision"] == "PENDING"
