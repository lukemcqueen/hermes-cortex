#!/usr/bin/env python3
"""Regression tests for check-hermes-upstream-fix.py watchdog logic.

Fleet incident 2026-08-25: upstream hermes-agent commit 2f33833de introduced
an inverted return in MCPServerTask._stdio_children_dead() (tools/mcp_tool.py)
— returned True when a tracked stdio child was ALIVE, fast-failing healthy
stdio MCP servers. The watchdog polls origin/main daily and notifies once
when the buggy marker is gone. These tests pin the detection logic: no
network, hermetic against sample source text. Sample bodies use a following
method to delimit the function (the parser requires a next `def` at the same
indent — matching real mcp_tool.py where the method is never last).
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "check_hermes_upstream_fix", _REPO / "ops" / "scripts" / "health" / "check-hermes-upstream-fix.py")
WD = importlib.util.module_from_spec(_SPEC)
sys.modules["check_hermes_upstream_fix"] = WD
_SPEC.loader.exec_module(WD)

# Realistic upstream shape: _stdio_children_dead followed by another method.
BUGGY_SRC = '''class MCPServerTask:
    def _stdio_children_dead(self):
        return True  # alive

    async def _run(self):
        pass
'''

FIXED_SRC = '''class MCPServerTask:
    def _stdio_children_dead(self):
        return False

    async def _run(self):
        pass
'''

STUB_SRC = '''class MCPServerTask:
    def _stdio_children_dead(self):
        pass

    async def _run(self):
        pass
'''


def test_buggy_marker_flagged_not_fixed():
    assert WD.is_fixed(BUGGY_SRC) is False


def test_function_absent_is_fixed():
    assert WD.is_fixed("class MCPServerTask:\n    async def _run(self):\n        pass\n") is True


def test_fixed_return_false_path_is_fixed():
    assert WD.is_fixed(FIXED_SRC) is True


def test_stub_with_no_returns_is_not_fixed():
    assert WD.is_fixed(STUB_SRC) is False


def test_conservative_when_function_is_last_in_file():
    # No following `def` to delimit the body -> parse fails -> NOT fixed.
    # Conservative by design: never wake the fleet on a false positive.
    last_in_file = '''class MCPServerTask:
    def _stdio_children_dead(self):
        return False
'''
    assert WD.is_fixed(last_in_file) is False


def test_fetch_failure_alerts_exit1(monkeypatch, capsys):
    def boom(url):
        raise OSError("network down")
    monkeypatch.setattr(WD, "fetch", boom)
    assert WD.main(["--dry-run"]) == 1
    err = capsys.readouterr().err
    assert "CHECK FAILED" in err


def test_dry_run_fixed_source_prints_notice_no_marker(monkeypatch, capsys):
    def fake_fetch(url):
        assert url == "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/mcp_tool.py"
        return FIXED_SRC
    monkeypatch.setattr(WD, "fetch", fake_fetch)
    assert WD.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "UPSTREAM FIX DETECTED" in out
    # dry-run must never write the dedupe marker
    assert not Path(WD.MARKER).exists()


def test_silent_when_bug_still_present(monkeypatch, capsys):
    def fake_fetch(url):
        return BUGGY_SRC
    monkeypatch.setattr(WD, "fetch", fake_fetch)
    assert WD.main(["--dry-run"]) == 0
    assert capsys.readouterr().out == ""
