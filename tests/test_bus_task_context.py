#!/usr/bin/env python3
"""Tests for bus task_delegation F13 context enrichment (cortex-bus-mcp).

When an orchestrator dispatches a task via inbox_send_task with a worktree,
the task_delegation body should carry a pre-fetched context envelope
(Dexter Horthy factor-13) — the receiving agent starts with repo rules +
plan + task + git history instead of fetching context itself.

Run: python3 -m pytest tests/test_bus_task_context.py -q
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
# Mirror the deployed layout: the builder lives next to the MCP servers on
# the fleet (~/.hermes-cortex/scripts/); in-repo it's ops/scripts/. Both
# must be importable so the direct import works in tests and in prod.
sys.path.insert(0, str(_REPO / "ops" / "scripts"))
_SPEC = importlib.util.spec_from_file_location(
    "cortex_bus_mcp", _REPO / "mcp-servers" / "cortex-bus-mcp.py")
_bus = importlib.util.module_from_spec(_SPEC)
try:
    _SPEC.loader.exec_module(_bus)
except Exception:  # heavy deps (MCP SDK) — helper testable if module loads
    _bus = None


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"],
                   check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"],
                   check=True)
    (tmp_path / "AGENTS.md").write_text("# Rules\n- R1: no bypass\n")
    (tmp_path / "CLAUDE.md").write_text("# Governance\n- same rules\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"],
                   check=True)
    return tmp_path


@pytest.mark.skipif(_bus is None, reason="cortex-bus-mcp imports MCP SDK")
def test_enrich_adds_context_when_worktree(git_repo):
    body = {"type": "task_delegation", "description": "fix the bug"}
    out = _bus._enrich_task_with_context(body, worktree=str(git_repo),
                                         plan="slice-1")
    assert "context_envelope" in out
    assert "R1: no bypass" in out["context_envelope"] or "AGENTS.md" in out["context_envelope"]
    assert "fix the bug" in out["context_envelope"]


@pytest.mark.skipif(_bus is None, reason="cortex-bus-mcp imports MCP SDK")
def test_enrich_keeps_body_light_without_worktree():
    body = {"type": "task_delegation", "description": "check health"}
    out = _bus._enrich_task_with_context(body, worktree="")
    assert "context_envelope" not in out


@pytest.mark.skipif(_bus is None, reason="cortex-bus-mcp imports MCP SDK")
def test_enrich_budgets_context(git_repo):
    body = {"type": "task_delegation", "description": "t"}
    out = _bus._enrich_task_with_context(body, worktree=str(git_repo),
                                         plan="p", max_chars=400)
    assert len(out["context_envelope"]) <= 400 + 50


@pytest.mark.skipif(_bus is None, reason="cortex-bus-mcp imports MCP SDK")
def test_enrich_never_raises_on_bad_repo():
    body = {"type": "task_delegation", "description": "t"}
    out = _bus._enrich_task_with_context(body, worktree="/nonexistent/repo",
                                         plan="p")
    assert "context_envelope" not in out  # fail-open, no crash
