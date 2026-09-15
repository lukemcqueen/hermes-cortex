#!/usr/bin/env python3
"""Tests that the doctor's immutable checks route through the
cross-platform probe (cortex_doctor/immutability.py) instead of calling
Linux-only lsattr directly — the macOS false-positive fix (2026-09-15).

Run: python3 -m pytest tests/test_doctor_immutability.py -q
"""
import sys
import inspect
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks, immutability  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


def test_immutable_check_uses_shared_probe_on_macos(monkeypatch, tmp_path):
    """On macOS, _check_enforcer_immutability must consult the shared
    probe (which knows chflags uchg), NOT shell out to lsattr directly.
    RED before fix: check called lsattr, so the probe was never consulted."""
    monkeypatch.setattr(checks, "IS_MAC", True)
    monkeypatch.setattr(checks, "IS_LINUX", False)
    f = tmp_path / "pre-commit"
    f.write_text("#!/bin/sh\n")
    called = []
    monkeypatch.setattr(checks, "is_file_immutable",
                        lambda p: called.append(str(p)) or True)

    res = Results()
    checks._check_enforcer_immutability(res, tmp_path / "none", tmp_path)
    assert called, "shared probe never consulted — check still probes lsattr directly"
    entry = next(c for c in res.checks if c["name"] == "Immutable: pre-commit")
    assert entry["status"] == "PASS", entry


def test_check_enforcer_immutability_macos_uchg_passes(monkeypatch, tmp_path):
    """Full behavior: on macOS with uchg set on a real file, the check
    PASSes (before fix it FAILed 'cannot verify')."""
    f = tmp_path / "pre-commit"
    f.write_text("#!/bin/sh\n")
    monkeypatch.setattr(checks, "IS_MAC", True)
    monkeypatch.setattr(checks, "IS_LINUX", False)

    monkeypatch.setattr(immutability, "_IS_MAC", True)
    monkeypatch.setattr(
        immutability.subprocess, "run",
        lambda argv, capture_output=True, text=True, timeout=5: type(
            "R", (), {"stdout": "-rwxr-xr-x 1 u s uchg 5 t " + str(f),
                      "returncode": 0})())
    # checks.py currently calls subprocess directly — after the fix it
    # must go through immutability.is_file_immutable, so also stub the
    # probe for pre-fix/post-fix coverage:

    def probe(path):
        return immutability.is_file_immutable(path)

    monkeypatch.setattr(checks, "is_file_immutable", probe, raising=False)

    res = Results()
    checks._check_enforcer_immutability(res, tmp_path / "none", tmp_path)
    entry = next((c for c in res.checks if c["name"] == "Immutable: pre-commit"), None)
    assert entry is not None
    assert entry["status"] == "PASS", entry
