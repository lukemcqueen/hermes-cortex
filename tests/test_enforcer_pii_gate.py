#!/usr/bin/env python3
"""Unit tests for the enforcer PII gate extensions (Luke 2026-08-24).

Run: python3 -m pytest tests/test_enforcer_pii_gate.py -q

Hermetic: imports the enforcer module, calls the gate logic directly
with synthetic args. PII strings are constructed at runtime (never
literal in the repo — the gate itself would block them). Verifies the
PII classes: emails, personal identifiers (surname/domain/full names),
phone numbers, private server URLs — while allowing the repo's own
URL, public job boards, functional usernames, placeholders, prose.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "enforcer", _REPO / "plugins" / "governance-enforcer" / "__init__.py")
enf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(enf)

# PII strings built at runtime so they never appear literally in the repo
SURNAME = "Mc" + "Queen"
DOMAIN = "realgospel" + "message.org"
FULLNAME = "Amy " + "Chu " + SURNAME


def gate(text: str) -> bool:
    """Run the PII gate against a write to the repo root; True = blocked."""
    args = {"path": str(_REPO / "docs" / "test.md"), "content": text}
    return enf._check_pii_content_gate("write_file", args) is not None


def _email(local, dom):
    return f"{local}@{dom}"


BLOCKED = [
    _email("luke", DOMAIN),
    f"Built by Luke {SURNAME} in Seoul",
    f"the bus at {DOMAIN}:13004",
    f"co-founder with {FULLNAME}",
    "call 010-1234-5678",
    "connect to https://my-secret-server.internal:8443",
    "panel at https://192.168.1.10/admin",
]

ALLOWED = [
    "clone https://github.com/fleet-operator/hermes-cortex",
    "role at https://openai.com/careers",
    "https://himalayas.app/jobs/countries/south-korea/ai",
    "routing to luke and amy inboxes",
    "admin@client-domain.com",
    "the fleet operates six agents autonomously",
    "docs at https://hermes-agent.nousresearch.com/docs",
]


@pytest.mark.parametrize("text", BLOCKED)
def test_pii_blocked(text):
    assert gate(text), f"should have blocked: {text[:50]}"


@pytest.mark.parametrize("text", ALLOWED)
def test_non_pii_allowed(text):
    assert not gate(text), f"should NOT have blocked: {text[:50]}"
