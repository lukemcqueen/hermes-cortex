#!/usr/bin/env python3
"""Unit tests for orch-task-board-digest.py (T4).

Run: python3 -m pytest tests/test_orch_task_board_digest.py -q

Hermetic: the task-db psql bridge is monkeypatched; no DB access.
Tests the digest rendering: counts, by-agent, review queue, claimable,
empty-board fallback, and error path.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "board_digest", _REPO / "ops" / "scripts" / "manage" / "orch-task-board-digest.py")
digest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(digest)


def _render(responses: dict[str, str], capsys) -> tuple[int, str]:
    """Run main() with a fake q() returning canned rows; capture stdout."""
    def fake_q(query: str, params: list | None = None) -> str:
        for key, val in responses.items():
            if key in query:
                return val
        return ""
    digest.q = fake_q
    rc = digest.main()
    out = capsys.readouterr().out
    return rc, out


def test_full_board(capsys):
    rc, out = _render({
        "GROUP BY status": "pending||14\nin_progress||3\nreview||2",
        "WHERE status = 'in_progress'": "esther||2\ntitus||1",
        "WHERE t.status = 'review'": "aaa11111||titus||content one",
        "AND t.assignee IS NULL": "bbb22222||2||client-brand-eng||claimable slice",
    }, capsys)
    assert rc == 0
    assert "Open: **19**" in out
    assert "14 pending" in out and "3 in_progress" in out and "2 review" in out
    assert "esther: 2" in out and "titus: 1" in out
    assert "awaiting verify" in out
    assert "aaa11111" in out
    assert "claimable slice" in out


def test_empty_board(capsys):
    rc, out = _render({}, capsys)
    assert rc == 0
    assert "Open: **0**" in out
    assert "No open tasks" in out


def test_gaps_never_zeros(capsys):
    """Agents with no in_progress must not appear as zeros."""
    rc, out = _render({
        "GROUP BY status": "pending||5",
        "WHERE status = 'in_progress'": "",
        "WHERE t.status = 'review'": "",
        "AND t.assignee IS NULL": "",
    }, capsys)
    assert rc == 0
    assert "Open: **5**" in out
    assert "In progress" not in out  # no agents listed when none busy


def test_error_path(capsys):
    def boom(query, params=None):
        raise RuntimeError("db down")
    digest.q = boom
    rc = digest.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "db down" in out
