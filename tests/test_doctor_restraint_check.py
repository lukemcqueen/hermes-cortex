#!/usr/bin/env python3
"""Tests for the doctor's guardrail-restraint presence check (Story M1.2).

check_restraint_registry must FAIL when a correction class's `restraint`
names an artifact that does not exist on disk (a doctor: check, a hook:, a
skill:, or an enforcer:), and PASS when every restraint resolves.

Run: python3 -m pytest tests/test_doctor_restraint_check.py -q
"""
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


def _write_registry(tmp_path, classes):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "guardrail-registry.json").write_text(json.dumps({"classes": classes}))


def _entry(res):
    return next((c for c in res.checks if c["name"] == "Restraint registry"), None)


def test_nonexistent_restraint_reports_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "CORTEX_REPO", tmp_path)
    _write_registry(tmp_path, {
        "verify-before-declare": {"restraint": "doctor:check_does_not_exist_xyz"},
    })
    res = Results()
    checks.check_restraint_registry(res)
    entry = _entry(res)
    assert entry is not None, "Restraint registry check not run"
    assert entry["status"] == "FAIL", entry
    assert "verify-before-declare" in entry["detail"]


def test_all_restraints_present_reports_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "CORTEX_REPO", tmp_path)
    _write_registry(tmp_path, {
        "verify-before-declare": {"restraint": "doctor:check_governance"},
    })
    res = Results()
    checks.check_restraint_registry(res)
    entry = _entry(res)
    assert entry is not None
    assert entry["status"] == "PASS", entry


def test_hook_and_skill_restraints_resolve(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "CORTEX_REPO", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_HOME", tmp_path / "cortex-home")
    monkeypatch.setattr(checks, "HERMES_HOME", tmp_path / "hermes-home")

    repo = tmp_path
    (repo / "ops" / "scripts").mkdir(parents=True)
    (repo / "ops" / "scripts" / "pre-commit-score").write_text("#!/bin/sh\n")
    skills = repo / "skills"
    (skills / "reflexion-check").mkdir(parents=True)
    (skills / "reflexion-check" / "SKILL.md").write_text("# skill\n")

    _write_registry(tmp_path, {
        "bypass-attempt": {"restraint": "hook:pre-commit-score"},
        "verify-before-declare": {"restraint": "skill:reflexion-check"},
    })
    res = Results()
    checks.check_restraint_registry(res)
    entry = _entry(res)
    assert entry is not None
    assert entry["status"] == "PASS", entry
