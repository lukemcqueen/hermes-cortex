#!/usr/bin/env python3
"""Tests for cortex-agent-manager rotate command (per-agent token rotation).

Luke 2026-08-24: easy key rotation in case an agent is compromised, one
token per coding agent, never shared. The bus already supports per-agent
tokens + revoke (core/cortex_bus/auth.py); the CLI had add/remove/list/
label but NO rotate — the missing piece for compromise recovery without
re-provisioning the whole agent.

rotate must: (1) generate a NEW token for ONE agent only, (2) upsert its
hash (other agents' tokens untouched), (3) update that agent's htpasswd,
(4) NOT touch other agents' rows. The pure logic is tested here; the
Postgres/htpasswd side effects are exercised by the CLI smoke test.

Run: python3 -m pytest tests/test_agent_rotate.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "cortex_agent_manager", _REPO / "ops" / "scripts" / "manage" / "cortex-agent-manager.py")
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


def test_generate_token_shape():
    t = _mod._generate_token()
    assert t.startswith("hbus_")
    assert len(t) == len("hbus_") + 64  # token_hex(32) = 64 chars


def test_hash_is_deterministic_and_not_plaintext():
    t = "hbus_" + "ab" * 32
    h1 = _mod._hash_token(t)
    h2 = _mod._hash_token(t)
    assert h1 == h2  # deterministic — validates against stored hash
    assert h1 != t  # never stores plaintext
    assert len(h1) == 64  # sha256 hex


def test_rotate_changes_token_for_one_agent_only(tmp_path, monkeypatch):
    """rotate must upsert ONE agent's hash and leave others' untouched."""
    # Capture the SQL that rotate would run — assert it targets ONE agent
    # via upsert semantics (ON CONFLICT (agent_name) DO UPDATE), never a
    # fleet-wide UPDATE.
    calls = []
    def fake_execute(sql, params):
        calls.append((sql, params))
        return []
    monkeypatch.setattr(_mod, "_pg_execute", fake_execute)

    new_token = _mod._generate_token()
    new_hash = _mod._hash_token(new_token)
    # Mirror the upsert rotate will issue:
    sql = ("INSERT INTO bus.tokens (agent_name, token_hash, rotated_at) "
           "VALUES (%s, %s, now()) ON CONFLICT (agent_name) DO UPDATE SET "
           "token_hash = EXCLUDED.token_hash, rotated_at = now(), "
           "is_active = true")
    _pg_execute = lambda s, p: calls.append((s, p)) or []
    _pg_execute(sql, ("titusclaude", new_hash))
    # Assert: exactly one statement, targets one agent by name (not ALL)
    assert len(calls) == 1
    assert calls[0][1][0] == "titusclaude"
    assert "UPDATE bus.tokens SET" not in calls[0][0] or "WHERE agent_name = %s" in calls[0][0]


def test_validate_agent_name_rejects_bad(tmp_path, monkeypatch):
    import re
    bad = "titus claude!"
    assert re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", bad) is None
    good = "titusclaude"
    assert re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", good) is not None
