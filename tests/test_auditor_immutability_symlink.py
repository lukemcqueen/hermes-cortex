#!/usr/bin/env python3
"""Regression test: auditor immutability check must resolve symlinks before
probing. On macOS `ls -lO` on a symlink reports the symlink's own (empty)
flag field, so a protected target was flagged as "missing" (Titus FP,
2026-09-15). The probe must receive the realpath.

The auditor file is hyphen-named (agent-governance-auditor.py) — loaded
via importlib with the repo's ops/scripts on sys.path for hermes_tz.

Run: python3 -m pytest tests/test_auditor_immutability_symlink.py -q
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_MANAGE = _REPO / "ops" / "scripts" / "manage"
for p in (str(_MANAGE), str(_REPO / "ops" / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_auditor():
    spec = importlib.util.spec_from_file_location(
        "agent_governance_auditor", _MANAGE / "agent-governance-auditor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aud = _load_auditor()
import cortex_doctor.immutability as imm  # noqa: E402


@pytest.fixture
def hook_layout(tmp_path, monkeypatch):
    """Fake HOME with .hermes-cortex/hooks/pre-commit -> target symlink."""
    hooks = tmp_path / ".hermes-cortex" / "hooks"
    hooks.mkdir(parents=True)
    target = tmp_path / "pre-commit-score"
    target.write_text("#!/bin/sh\n")
    (hooks / "pre-commit").symlink_to(target)
    monkeypatch.setenv("HOME", str(tmp_path))
    return hooks, target


def test_probes_realpath_not_symlink(monkeypatch, hook_layout):
    hooks, target = hook_layout
    probed = []
    monkeypatch.setattr(imm, "is_file_immutable",
                        lambda p: probed.append(str(p)) or True)
    issues = aud._check_infrastructure()
    assert probed, "probe never called"
    assert str(target) in probed, f"probe got symlink path, not realpath: {probed}"
    assert not any("Immutable flag MISSING" in i for i in issues), issues


def test_unprotected_target_still_flagged(monkeypatch, hook_layout):
    hooks, target = hook_layout
    monkeypatch.setattr(imm, "is_file_immutable", lambda p: False)
    issues = aud._check_infrastructure()
    assert any("Immutable flag MISSING" in i for i in issues), issues
    hit = next(i for i in issues if "Immutable flag MISSING" in i)
    assert str(target) in hit, f"issue should name the resolved target: {hit}"


def test_broken_symlink_skipped_gracefully(monkeypatch, tmp_path):
    hooks = tmp_path / ".hermes-cortex" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").symlink_to(tmp_path / "nonexistent")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(imm, "is_file_immutable",
                        lambda p: (_ for _ in ()).throw(OSError("boom")))
    issues = aud._check_infrastructure()  # must not raise
    assert isinstance(issues, list)
