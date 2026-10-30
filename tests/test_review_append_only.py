"""Hermetic tests: adversarial_reviews is APPEND-ONLY with a sanctioned re-review.

WHY (2026-10-30, operator directive): a worker was observed doing
`DELETE FROM adversarial_reviews WHERE cycle_id=8208;` via raw sqlite3 to clear
a FINDINGS verdict, then re-recording — the re-roll-until-CLEAN loophole and an
audit-tamper. The store must be append-only, and the legitimate need (a fresh
verdict after improving the material) is served by --re-review, which MOVES the
old verdict into `adversarial_reviews_history` (append-only) and records a fresh
current row. Nothing is ever deleted.

The close-time reviewer (loop-gov-mcp.py) depends on ONE current row per cycle
(cycle_id UNIQUE + ON CONFLICT(cycle_id) DO UPDATE + a bare fetchone()), so the
primary table keeps its UNIQUE — only re-review moves rows to history.

These tests drive the reviewer module's OWN `_record()` against a temp DB —
never the live store. Run: python3 -m pytest tests/test_review_append_only.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = (Path(__file__).resolve().parents[1]
           / "ops" / "scripts" / "orch-bus" / "adversarial-review.py")
_spec = importlib.util.spec_from_file_location("adv_review_append", _SCRIPT)
assert _spec and _spec.loader, f"cannot load {_SCRIPT}"
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _db(tmp_path):
    return tmp_path / "loop-governance.db"


def _record(db, cycle_id=101, verdict_text=None, re_review=False):
    """Drive _record() with a canned reviewer reply."""
    text = verdict_text or (
        'Here is the review:\n```json\n{"cycle_id": %d, "verdict": "FINDINGS",'
        ' "findings": [{"severity": "high", "target": "x", "recommendation": "y"}],'
        ' "summary": "s"}\n```' % cycle_id)
    return mod._record(db, cycle_id, "reviewer-A", "deepseek/deepseek-v4-pro",
                       text, re_review=re_review)


_COUNT_SQL = {
    "adversarial_reviews": "SELECT COUNT(*) FROM adversarial_reviews",
    "adversarial_reviews_history": "SELECT COUNT(*) FROM adversarial_reviews_history",
}


def _count(db, table):
    """Count rows in one of the two known tables — fixed SQL map, never
    interpolate the table name (keeps the adversarial scanner clean)."""
    c = sqlite3.connect(str(db))
    try:
        return c.execute(_COUNT_SQL[table]).fetchone()[0]
    finally:
        c.close()


def _current(db, cycle_id):
    c = sqlite3.connect(str(db))
    try:
        row = c.execute("SELECT verdict FROM adversarial_reviews "
                       "WHERE cycle_id=?", (cycle_id,)).fetchone()
        return row[0] if row else None
    finally:
        c.close()


def _history(db, cycle_id):
    c = sqlite3.connect(str(db))
    try:
        row = c.execute("SELECT verdict, reason, superseded_ts FROM "
                        "adversarial_reviews_history WHERE cycle_id=?",
                        (cycle_id,)).fetchone()
        return row
    finally:
        c.close()


# ── first review inserts a current row, no history ─────────────────────────

def test_first_review_inserts_current_row_no_history(tmp_path):
    db = _db(tmp_path)
    assert _record(db) == 0
    assert _current(db, 101) == "FINDINGS"
    assert _count(db, "adversarial_reviews") == 1
    assert _count(db, "adversarial_reviews_history") == 0


# ── plain --review on an already-reviewed cycle is a benign no-op ─────────

def test_plain_review_on_reviewed_cycle_is_noop(tmp_path):
    db = _db(tmp_path)
    assert _record(db) == 0
    # Same verdict text again — a plain --review must NOT overwrite or duplicate.
    assert _record(db) == 0
    assert _count(db, "adversarial_reviews") == 1
    assert _count(db, "adversarial_reviews_history") == 0
    assert _current(db, 101) == "FINDINGS"


# ── the append-only invariant: --re-review moves, never deletes ───────────

def test_rereview_moves_old_verdict_into_history(tmp_path):
    db = _db(tmp_path)
    assert _record(db, 202) == 0            # FINDINGS verdict first
    # Then a fresh CLEAN verdict (distinct text).
    assert _record(db, 202, re_review=True,
                   verdict_text='{"verdict": "CLEAN", "findings": [], '
                                 '"summary": "committed proof now clean"}') == 0
    # One CURRENT row (the fresh verdict), one HISTORY row (the old FINDINGS).
    assert _count(db, "adversarial_reviews") == 1
    assert _count(db, "adversarial_reviews_history") == 1
    assert _current(db, 202) == "CLEAN"
    old, reason, ts = _history(db, 202)
    assert old == "FINDINGS"
    assert reason == "re-review"
    assert ts, "superseded_ts must be set"


def test_rereview_history_accumulates_over_multiple_judgements(tmp_path):
    db = _db(tmp_path)
    for _ in range(3):
        assert _record(db, 303, re_review=True) == 0
    assert _count(db, "adversarial_reviews") == 1
    assert _count(db, "adversarial_reviews_history") == 2  # superseded twice


def test_rereview_on_cycle_with_no_prior_review_is_plain_insert(tmp_path):
    db = _db(tmp_path)
    assert _record(db, 404, re_review=True) == 0
    assert _count(db, "adversarial_reviews") == 1
    assert _count(db, "adversarial_reviews_history") == 0


# ── schema sanity: both tables created and self-consistent ─────────────────

def test_history_table_is_created_by_first_record(tmp_path):
    db = _db(tmp_path)
    assert _record(db) == 0
    c = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "adversarial_reviews" in tables
        assert "adversarial_reviews_history" in tables
    finally:
        c.close()


def test_reviewer_json_extraction_still_works_on_canned_reply():
    findings, verdict = mod._extract_reviewer_json(
        '{"verdict": "CLEAN", "findings": [], "summary": "ok"}')
    assert verdict == "CLEAN"
    assert json.loads(findings) == []
