#!/usr/bin/env python3
"""Tests for the doctor's bus-grant expiry check (Story M5.2).

check_bus_grant_expiry WARNS when a bus.permissions grant has expires_at NULL
(indefinite) and no named justifier (config.indefinite_justification or
labels.indefinite).

Run: python3 -m pytest tests/test_doctor_grant_expiry.py -q
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


def _entry(res):
    return next((c for c in res.checks if c["name"] == "Bus grant expiry"), None)


def test_find_unjustified_indefinite_pure():
    grants = [
        {"agent_name": "a", "expires_at": None, "config": {}},
        {"agent_name": "b", "expires_at": "2026-01-01T00:00:00+00:00", "config": {}},
        {"agent_name": "c", "expires_at": None, "config": {"indefinite_justification": "orchestrator"}},
        {"agent_name": "d", "expires_at": None, "labels": {"indefinite": True}},
    ]
    assert checks._find_unjustified_indefinite(grants) == ["a"]


def test_unjustified_indefinite_grant_warns(monkeypatch):
    monkeypatch.setattr(checks, "_query_bus_grants", lambda: [
        {"agent_name": "moses", "expires_at": None, "config": {}},
    ])
    res = Results()
    checks.check_bus_grant_expiry(res)
    entry = _entry(res)
    assert entry is not None, "Bus grant expiry check not run"
    assert entry["status"] == "WARN", entry
    assert "moses" in entry["detail"]


def test_justified_indefinite_grant_passes(monkeypatch):
    monkeypatch.setattr(checks, "_query_bus_grants", lambda: [
        {"agent_name": "moses", "expires_at": None,
         "config": {"indefinite_justification": "orchestrator runs permanently"}},
    ])
    res = Results()
    checks.check_bus_grant_expiry(res)
    entry = _entry(res)
    assert entry is not None
    assert entry["status"] == "PASS", entry


def test_unqueryable_bus_skips(monkeypatch):
    monkeypatch.setattr(checks, "_query_bus_grants", lambda: None)
    res = Results()
    checks.check_bus_grant_expiry(res)
    entry = _entry(res)
    assert entry is not None
    assert entry["status"] == "SKIP", entry
