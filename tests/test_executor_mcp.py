#!/usr/bin/env python3
"""Unit tests for executor-mcp.py (executor MCP server + HermesAdapter).

Run: python3 -m pytest tests/test_executor_mcp.py -q

Hermetic: imports executor-mcp as a module, tests the registry, routing,
policy gate, and HermesAdapter result-shaping WITHOUT an MCP transport or
live executors. The tool definitions + handler dispatch are covered by
direct calls to list_tools()/call handlers.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "executor_mcp", _REPO / "mcp-servers" / "executor-mcp.py")
em = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(em)


# ── Registry tests ────────────────────────────────────────────

def test_registry_starts_with_hermes():
    ids = [e["executor_id"] for e in em._registry]
    assert "hermes" in ids


def test_register_executor():
    before = len(em._registry)
    em._register_executor({
        "executor_id": "test-claude",
        "type": "claude",
        "host": "<test-host>",
        "models": ["sonnet"],
        "capabilities": ["code.read", "code.write"],
        "data_tiers": ["none", "projects"],
        "cost_profile": {"sonnet": 0.05},
        "health_endpoint": "http://<test-host>:8911/health",
    })
    after = len(em._registry)
    assert after == before + 1
    em._registry = [e for e in em._registry if e["executor_id"] != "test-claude"]


def test_duplicate_register_rejected():
    with pytest.raises(ValueError):
        em._register_executor({"executor_id": "hermes", "type": "hermes"})


# ── Routing tests ─────────────────────────────────────────────

def test_route_capability_match():
    req = {
        "profile": "coding",
        "capabilities_required": ["code.read", "code.write", "tests"],
        "data_tier": "projects",
    }
    executor = em._route(req, _eligible=[{"executor_id": "hermes",
                                          "capabilities": ["code.read", "code.write",
                                                           "shell", "tests", "git"],
                                          "data_tiers": ["none", "projects"]}])
    assert executor == "hermes"


def test_route_no_match_returns_none():
    req = {"capabilities_required": ["code.write"], "data_tier": "projects"}
    executor = em._route(req, _eligible=[{"executor_id": "x",
                                          "capabilities": ["code.read"],
                                          "data_tiers": ["none"]}])
    assert executor is None


def test_route_denied_tier():
    req = {"capabilities_required": ["code.write"], "data_tier": "full"}
    executor = em._route(req, _eligible=[{"executor_id": "hermes",
                                          "capabilities": ["code.write"],
                                          "data_tiers": ["none", "projects"]}])
    assert executor is None


# ── Policy gate tests ─────────────────────────────────────────

def test_policy_gate_requires_governance_lock(monkeypatch):
    monkeypatch.setattr(em, "_governance_lock_open", lambda: False)
    result = em._execution_request({
        "executor_id": "hermes",
        "task": "do the thing",
        "repo": "/tmp/repo",
        "data_tier": "projects",
    })
    assert result.is_error is True
    assert "governance" in str(result.content[0].text).lower()


def test_policy_gate_denies_full_tier_for_worker(monkeypatch):
    monkeypatch.setattr(em, "_governance_lock_open", lambda: True)
    monkeypatch.setattr(em, "_is_orchestrator", lambda: False)
    result = em._execution_request({
        "executor_id": "hermes",
        "task": "do the thing",
        "repo": "/tmp/repo",
        "data_tier": "full",
    })
    assert result.is_error is True
    assert "data_tier" in str(result.content[0].text).lower()


# ── HermesAdapter result-shaping tests ────────────────────────

def test_hermes_result_shape():
    import time as _t
    handle = {"request_id": "req-1", "worktree": "/tmp/wt",
              "branch": "agent/hermes-req-1", "started_at": _t.time()}
    result = em._hermes_collect(handle)
    assert result["status"] == "success"
    assert result["worker"] == "hermes"
    assert result["request_id"] == "req-1"
    assert result["branch"] == "agent/hermes-req-1"
    assert result["needs_review"] is True
    assert "duration_s" in result
    assert "cost" in result


def test_hermes_collect_requires_worktree():
    handle = {"request_id": "req-2"}
    result = em._hermes_collect(handle)
    assert result["status"] == "failed"
    assert "worktree" in result.get("error", "")


# ── Tool surface tests ────────────────────────────────────────

def test_list_tools_exposes_six_tools():
    import asyncio
    tools = asyncio.run(em.list_tools(None))
    names = [t.name for t in tools.tools]
    assert "executor_list" in names
    assert "executor_probe" in names
    assert "execution_request" in names
    assert "execution_status" in names
    assert "execution_cancel" in names
    assert "execution_collect" in names


def test_executor_list_returns_cards():
    result = em._executor_list({})
    assert result.is_error is False
    text = str(result.content[0].text)
    assert "hermes" in text


def test_unknown_executor_probe():
    result = em._executor_probe({"executor_id": "does-not-exist"})
    assert result.is_error is True
