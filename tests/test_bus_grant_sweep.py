#!/usr/bin/env python3
"""Tests for ops/scripts/manage/bus-grant-sweep.py (Story M5.1).

The sweep lists grants whose expires_at is in the past; future and indefinite
(NULL) grants are omitted. Hyphenated script → loaded via importlib and
exercised through subprocess against a --grants-file fixture.

Run: python3 -m pytest tests/test_bus_grant_sweep.py -q
"""
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage" / "bus-grant-sweep.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("bus_grant_sweep", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sweep_lists_past_omits_future_and_indefinite():
    mod = _load_module()
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    grants = [
        {"agent_name": "past", "expires_at": "2026-09-23T00:00:00+00:00"},
        {"agent_name": "future", "expires_at": "2026-09-25T00:00:00+00:00"},
        {"agent_name": "indefinite", "expires_at": None},
    ]
    expired = mod.sweep_expired(grants, now=now)
    assert [g["agent_name"] for g in expired] == ["past"]


def test_sweep_cli_lists_past_grant(tmp_path):
    p = tmp_path / "grants.json"
    p.write_text(json.dumps([
        {"agent_name": "old-grant", "expires_at": "2026-01-01T00:00:00+00:00"},
        {"agent_name": "fresh-grant", "expires_at": "2099-01-01T00:00:00+00:00"},
    ]))
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--grants-file", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "old-grant" in r.stdout
    assert "fresh-grant" not in r.stdout


def test_sweep_empty_grants_prints_nothing(tmp_path):
    p = tmp_path / "grants.json"
    p.write_text(json.dumps([]))
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--grants-file", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "old-grant" not in r.stdout
