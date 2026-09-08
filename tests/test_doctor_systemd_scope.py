#!/usr/bin/env python3
"""Tests for the doctor's Systemd-scope check being design-aware.

2026-09-08: the doctor unconditionally WARNed whenever any
hermes-*.service existed in /etc/systemd/system/, assuming user-scope
(~/.config/systemd/user/) is always correct. But cortex-update.sh is
explicitly SCOPE-AWARE: on migrated hosts, Hermes gateway + cortex-bus +
dashboard + health-vector run as SYSTEM units (multi-user.target) by
design (2026-09-01 decision on moses after the user-scope boot
port-fight).

A flat WARN on system units is a false positive on those hosts, and its
suggested remediation (sudo rm /etc/systemd/system/hermes-*.service)
would actively break the running gateway/dashboard.

Fix: the check is design-aware — PASS when system Hermes units are
present AND active (valid migrated-host system scope). WARN only when a
system Hermes unit file exists but is NOT active (a stale/misconfigured
unit that could indicate a real scope problem).

Run: python3 -m pytest tests/test_doctor_systemd_scope.py -q
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


def _scope_status(res):
    for c in res.checks:
        if c["name"] == "Systemd scope":
            return c["status"]
    return None


@pytest.fixture
def scope_fixture(monkeypatch):
    """Stub IS_LINUX + run_bg so only the systemd-scope branch is exercised."""
    monkeypatch.setattr(checks, "IS_LINUX", True)
    real_check = checks.check_system

    def make_run_bg(units, active):
        def fake_run_bg(cmd, timeout=10):
            s = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "ls /etc/systemd/system/hermes-" in s:
                return units
            if cmd[:1] == ["df", "-h", "/"]:
                return "Filesystem Size Used Avail Use% Mounted\n/dev/x 100G 4G 96G 4% /\n"
            if "is-active" in s:
                return active
            return ""

        return fake_run_bg

    # We'll set run_bg per-test; provide a helper to run check_system safely.
    return make_run_bg


def test_inactive_system_unit_warns(monkeypatch, scope_fixture):
    """A system Hermes unit in a FAILED state is a real problem => WARN."""
    units = (
        "/etc/systemd/system/hermes-gateway.service\n"
        "/etc/systemd/system/hermes-cortex-dashboard.service\n"
    )
    fake = scope_fixture(units, "failed")
    monkeypatch.setattr(checks, "run_bg", fake)

    res = Results()
    checks.check_system(res)
    st = _scope_status(res)
    assert st == "WARN", (
        "A failed system Hermes unit is a genuine scope problem and must WARN, "
        f"got {st}."
    )


def test_masked_unit_does_not_warn(monkeypatch, scope_fixture):
    """A deliberately-masked unit (hermes-user-boot → /dev/null) must NOT warn."""
    units = "/etc/systemd/system/hermes-user-boot.service\n"
    fake = scope_fixture(units, "inactive")
    monkeypatch.setattr(checks, "run_bg", fake)

    res = Results()
    checks.check_system(res)
    st = _scope_status(res)
    assert st == "PASS", (
        "A masked/inactive system unit (deliberate disable) must PASS, "
        f"got {st}."
    )


def test_no_system_units_passes(monkeypatch, scope_fixture):
    """No system Hermes units => PASS (all user-level)."""
    fake = scope_fixture("", "inactive")
    monkeypatch.setattr(checks, "run_bg", fake)

    res = Results()
    checks.check_system(res)
    assert _scope_status(res) == "PASS", "No system units should PASS (user-level)."


def test_active_system_scope_passes(monkeypatch, scope_fixture):
    """3 active system Hermes units (migrated-host design) => PASS, not WARN."""
    units = (
        "/etc/systemd/system/hermes-gateway.service\n"
        "/etc/systemd/system/hermes-cortex-dashboard.service\n"
        "/etc/systemd/system/cortex-bus.service\n"
    )
    fake = scope_fixture(units, "active")
    monkeypatch.setattr(checks, "run_bg", fake)

    res = Results()
    checks.check_system(res)
    assert _scope_status(res) == "PASS", (
        "Active system-scope Hermes services (migrated-host design) must PASS, "
        "not WARN — the flat user-scope assumption is a false positive."
    )
