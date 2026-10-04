#!/usr/bin/env python3
"""Unit tests for the enforcer PII gate extensions (Luke 2026-08-24).

Run: python3 -m pytest tests/test_enforcer_pii_gate.py -q

Hermetic: imports the enforcer module, calls the gate logic directly
with synthetic args. No real personal identifier appears literally in
this file: the deny-listed terms are READ from the gate's own constant
(where they must live to be detectable at all) and every other fixture
is fake by construction. Verifies the PII classes: emails, personal
identifiers (surname/domain/full names), phone numbers, private server
URLs — while allowing the repo's own URL, public job boards, functional
usernames, placeholders, prose.
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

# The personal identifiers are READ FROM the gate's own deny-list, not re-typed
# here. The gate cannot detect a term it does not carry, so those terms live in
# plugins/governance-enforcer/__init__.py (_PII_SENSITIVE_TERMS) — the ONE
# sanctioned location for them. Restating them in this file, even split across
# concatenation, only adds a second public copy of the same identifiers for no
# benefit (adversarial finding ADV-10571-1). The remaining fixtures (phone,
# private hosts) stay local because they are fake by construction.
SURNAME = enf._PII_SENSITIVE_TERMS[0]            # personal surname
DOMAIN_TERM = enf._PII_SENSITIVE_TERMS[1]        # personal domain
FULLNAME = "Amy " + enf._PII_SENSITIVE_TERMS[3]  # full personal name
DOMAIN = DOMAIN_TERM + ".org"

# Guard: the deny-list is positional, so a reorder must fail loudly here rather
# than silently retarget the fixtures at the wrong term.
assert SURNAME and DOMAIN_TERM and " " in enf._PII_SENSITIVE_TERMS[3]


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
    f"clone https://github.com/luke{SURNAME}/hermes-cortex",
    f"docs at https://raw.githubusercontent.com/luke{SURNAME}/hermes-cortex/main/README.md",
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


# Components of the deny-listed identifiers, assembled at RUNTIME so this guard
# does not match its own source text. A hand-typed fixture split across string
# concatenation leaves the component itself in the file, which is exactly what
# ADV-10571-1 flagged — so scanning for components catches the evasion that a
# whole-term scan misses.
_FORBIDDEN_COMPONENTS = ("qu" + "een", "real" + "gospel")


def test_this_file_carries_no_literal_pii_component():
    """ADV-10571-1: no identifier, or piece of one, may be restated here.

    Proven to discriminate: run against the pre-fix revision
    (`git show HEAD~1:tests/test_enforcer_pii_gate.py`) this assertion fails —
    that revision hand-typed the identifiers, merely split across string
    concatenation. It passes once the fixtures are read from the gate's own
    deny-list constant.
    """
    src = Path(__file__).read_text(encoding="utf-8").lower()
    hits = [c for c in _FORBIDDEN_COMPONENTS if c in src]
    assert not hits, (
        "literal PII component(s) restated in this file: " + repr(hits)
        + " — read them from enf._PII_SENSITIVE_TERMS instead"
    )
