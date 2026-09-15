#!/usr/bin/env python3
"""Tests for the cross-platform immutability probe (cortex_doctor/immutability.py).

2026-09-15: the doctor's immutable check probed with Linux-only lsattr;
on macOS (Titus) every enforcement file WARNed/FAILed "cannot verify"
even though the files WERE protected via chflags uchg. Fix: a shared
probe — lsattr on Linux, `ls -lO` uchg on macOS.

Run: python3 -m pytest tests/test_doctor_immutability.py -q
"""
import sys
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import immutability  # noqa: E402


def _run_probe(monkeypatch, is_mac, cmd, stdout, returncode=0):
    """Point immutability at a fake OS and fake subprocess; return probe
    result + the argv actually executed."""
    calls = []

    def fake_run(argv, capture_output=True, text=True, timeout=5):
        calls.append(argv)
        class R:
            pass
        r = R()
        r.stdout = stdout
        r.returncode = returncode
        return r

    monkeypatch.setattr(immutability, "_IS_MAC", is_mac)
    monkeypatch.setattr(immutability.subprocess, "run", fake_run)
    result = immutability.is_file_immutable("/tmp/x")
    return result, calls


def test_macos_uchg_set_is_immutable(monkeypatch):
    # RED first run: macOS branch did not exist — lsattr was called, or
    # helper raised/returned wrong. After fix: uses `ls -lO`, sees uchg.
    result, calls = _run_probe(
        monkeypatch, True,
        ["ls", "-lO", "/tmp/x"],
        "-r--r--r--@ 1 root wheel uchg 1234 Jan 1 00:00 /tmp/x",
    )
    assert result is True
    assert calls[0][0] == "ls" and calls[0][1] == "-lO"


def test_macos_no_uchg_not_immutable(monkeypatch):
    result, calls = _run_probe(
        monkeypatch, True,
        ["ls", "-lO", "/tmp/x"],
        "-rw-r--r--@ 1 root wheel - 1234 Jan 1 00:00 /tmp/x",
    )
    assert result is False
    assert calls[0][0] == "ls"


def test_linux_i_flag_is_immutable(monkeypatch):
    result, calls = _run_probe(
        monkeypatch, False,
        ["lsattr", "/tmp/x"],
        "----i--------- /tmp/x",
    )
    assert result is True
    assert calls[0][0] == "lsattr"


def test_linux_no_i_flag_not_immutable(monkeypatch):
    result, _ = _run_probe(
        monkeypatch, False,
        ["lsattr", "/tmp/x"],
        "-------------- /tmp/x",
    )
    assert result is False


def test_probe_failure_raises_not_silent_pass(monkeypatch):
    # P12: a check that cannot verify must raise (caller WARNs), never
    # silently return False.
    def fake_run(argv, capture_output=True, text=True, timeout=5):
        class R:
            returncode = 1
            stdout = ""
        return R()

    monkeypatch.setattr(immutability, "_IS_MAC", False)
    monkeypatch.setattr(immutability.subprocess, "run", fake_run)
    with pytest.raises(OSError):
        immutability.is_file_immutable("/tmp/x")


def test_remediation_per_os(monkeypatch):
    monkeypatch.setattr(immutability, "_IS_MAC", True)
    assert "chflags uchg" in immutability.immutable_remediation("/p")
    monkeypatch.setattr(immutability, "_IS_MAC", False)
    assert "chattr +i" in immutability.immutable_remediation("/p")


def test_live_linux_probe_against_repo_file():
    # Live check on this Linux host: a plain (unlocked) file must probe
    # False without raising; the probe must not mistake "tool missing"
    # for "not immutable".
    probe = immutability.is_file_immutable(_REPO / "AGENTS.md")
    assert probe is False
