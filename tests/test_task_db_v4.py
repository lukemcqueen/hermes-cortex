#!/usr/bin/env python3
"""Unit tests for task model v3 CLI commands (T2) — claim/unclaim/report/verify.

Run: python3 -m pytest tests/test_task_db_v4.py -q

Tests the command dispatch and arg validation WITHOUT hitting a DB
(hermetic — the psql helper is mocked at the subprocess boundary).
The DB-level lifecycle is covered by tests/test-tasks-schema.sh
(AC-L1-22) which runs against the hermetic scratch DB.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "task_db", _REPO / "ops" / "scripts" / "manage" / "task-db.py")
task_db = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_db)


class FakePsql:
    """Capture psql calls; return canned output per query."""
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, query, params=None, role=None, timeout=15):
        self.calls.append((query, params, role))
        for key, val in self.responses.items():
            if key in query:
                return val
        return ""


@pytest.fixture(autouse=True)
def fake_psql(monkeypatch):
    f = FakePsql({"claim_slice": "t", "unclaim_slice": "t",
                  "report_done": "t", "verify_slice": "t"})
    monkeypatch.setattr(task_db, "psql", f)
    monkeypatch.setattr(task_db, "_require_v4", lambda x: None)
    monkeypatch.setattr(task_db, "PROFILE", "esther")
    return f


def test_claim_calls_function_with_agent(fake_psql):
    task_db.cmd_claim("11111111-2222-3333-4444-555555555555")
    q, params, _ = fake_psql.calls[-1]
    assert "claim_slice" in q
    assert params == ["11111111-2222-3333-4444-555555555555", "esther"]


def test_unclaim_calls_function_with_reason(fake_psql):
    task_db.cmd_unclaim("11111111-2222-3333-4444-555555555555", "blocked on deps")
    q, params, _ = fake_psql.calls[-1]
    assert "unclaim_slice" in q
    assert params[0] == "11111111-2222-3333-4444-555555555555"
    assert params[1] == "blocked on deps"


def test_report_calls_function_with_evidence(fake_psql):
    task_db.cmd_report("11111111-2222-3333-4444-555555555555", "tests pass")
    q, params, _ = fake_psql.calls[-1]
    assert "report_done" in q
    assert params[1] == "tests pass"


def test_verify_approve(fake_psql):
    task_db.cmd_verify("11111111-2222-3333-4444-555555555555", True, "ok")
    q, params, _ = fake_psql.calls[-1]
    assert "verify_slice" in q
    assert params == ["11111111-2222-3333-4444-555555555555", True, "ok"]


def test_verify_reject(fake_psql):
    task_db.cmd_verify("11111111-2222-3333-4444-555555555555", False, "weak")
    q, params, _ = fake_psql.calls[-1]
    assert params == ["11111111-2222-3333-4444-555555555555", False, "weak"]


def test_claim_failure_exits(capsys):
    import pytest as pt
    from unittest.mock import patch
    with patch.object(task_db, "psql", return_value="f"):
        with pt.raises(SystemExit) as e:
            task_db.cmd_claim("11111111-2222-3333-4444-555555555555")
        assert e.value.code == 1
        err = capsys.readouterr().err
        assert "Could not claim" in err


def test_invalid_uuid_rejected():
    import pytest as pt
    with pt.raises(SystemExit):
        task_db.cmd_claim("not-a-uuid")
