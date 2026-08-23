#!/usr/bin/env python3
"""Unit tests for orch-compete-run.py (T7) — compete mode contract.

Run: python3 -m pytest tests/test_orch_compete_run.py -q

Tests plan parsing, approach counting, and validation errors. The actual
delegation + judging happens in the orchestrator session (delegate_task
is a tool, not a script) — this validates the runner's contract.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "compete_run", _REPO / "ops" / "scripts" / "manage" / "orch-compete-run.py")
cr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cr)


def test_requires_slice_id(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orch-compete-run.py"])
    rc = cr.main()
    assert rc == 1


def test_requires_plan(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orch-compete-run.py", "run", "abc123"])
    rc = cr.main()
    assert rc == 1
    assert "--plan required" in capsys.readouterr().err


def test_requires_two_approaches(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orch-compete-run.py", "run", "abc123",
                                      "--plan", "APPROACH: only one"])
    rc = cr.main()
    assert rc == 1
    assert "≥2 APPROACH" in capsys.readouterr().err


def test_parses_approaches(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orch-compete-run.py", "run", "abc123",
                                      "--plan",
                                      "APPROACH: build in-house\n"
                                      "APPROACH: vendor integration\n"
                                      "some criteria line"])
    rc = cr.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 approaches" in out
    assert "build in-house" in out
    assert "vendor integration" in out
