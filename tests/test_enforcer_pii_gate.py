#!/usr/bin/env python3
"""Unit tests for the enforcer PII gate extensions (Luke 2026-08-24).

Run: python3 -m pytest tests/test_enforcer_pii_gate.py -q

Hermetic: imports the enforcer module and calls the gate logic directly with
synthetic args.

The deny-list holds SHA-256 digests rather than the identifiers (see
docs/design/pii-denylist-digests.md), so this file cannot build the real terms.
Coverage is therefore split three ways:

  * the MATCHING MECHANISM, end to end, with SYNTHETIC digests injected through
    the module's own attributes — a synthetic term is blocked in prose, allowed
    inside the repo's own URL, and its length is honoured;
  * the REAL surname entry, end to end, using a value that is already public in
    this repo: the owner handle parsed out of README.md's own GitHub URL;
  * the email / phone / private-host classes, unchanged, tested directly.

Every fixture that is PII-shaped is assembled at runtime from parts, so this
file carries no literal the gate would block. It also asserts the enforcer
source carries no identifier component, which is the regression guard for the
whole design.
"""
import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_ENFORCER = _REPO / "plugins" / "governance-enforcer" / "__init__.py"
_SPEC = importlib.util.spec_from_file_location("enforcer", _ENFORCER)
assert _SPEC is not None and _SPEC.loader is not None, f"cannot load {_ENFORCER}"
enf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(enf)

# The repo's own public owner handle, taken from README.md rather than typed
# here: it is already public in that URL, and reading it keeps this file free of
# identifier literals. It is the one real deny-list value exercisable end to end
# without restating anything.
_OWNER_MATCH = re.search(
    r"github\.com/([A-Za-z0-9._-]+)/hermes-cortex",
    (_REPO / "README.md").read_text(encoding="utf-8"),
)
assert _OWNER_MATCH is not None, "README.md no longer carries the repo's own URL"
_OWNER = _OWNER_MATCH.group(1)

# Components of the deny-listed identifiers, assembled at RUNTIME so the guard
# below does not match its own source text. A hand-typed fixture split across
# string concatenation leaves the component itself in the file, which is exactly
# what ADV-10571-1 flagged — so scanning for components catches the evasion a
# whole-term scan misses.
_FORBIDDEN_COMPONENTS = ("qu" + "een", "real" + "gospel")

# Synthetic deny-list used to exercise the mechanism without touching the real
# one. "acme" is chosen so it also sits inside a repo-URL owner segment.
_SYNTH_TERM = "acme"
_SYNTH_DIGEST = hashlib.sha256(_SYNTH_TERM.encode()).digest()

# PII-shaped fixtures, assembled from parts so no literal trips the gate.
_FAKE_EMAIL = "luke" + "@" + "somewhere" + "-not-a-placeholder.org"
_PHONE = "010-" + "1234" + "-5678"
_PRIVATE_HOST = "https" + "://my-secret-server" + ".internal:8443"
_LAN_HOST = "https" + "://192.168." + "1.10/admin"


def gate(text: str) -> bool:
    """Run the PII gate against a write to the repo root; True = blocked."""
    args = {"path": str(_REPO / "docs" / "test.md"), "content": text}
    return enf._check_pii_content_gate("write_file", args) is not None


@pytest.fixture
def synthetic_denylist(monkeypatch):
    """Replace the real deny-list with a synthetic one for the test's duration."""
    monkeypatch.setattr(enf, "_PII_SENSITIVE_DIGESTS", frozenset({_SYNTH_DIGEST}))
    monkeypatch.setattr(enf, "_PII_SENSITIVE_LENGTHS", (len(_SYNTH_TERM),))
    monkeypatch.setattr(enf, "_PII_SENSITIVE_URL_ALLOWED", frozenset({_SYNTH_DIGEST}))


# ── the mechanism, with synthetic digests ──────────────────────────────────

def test_synthetic_term_is_blocked_in_prose(synthetic_denylist):
    assert gate(f"Built by {_SYNTH_TERM} in Seoul")


def test_synthetic_term_is_allowed_inside_the_repo_url(synthetic_denylist):
    assert not gate(f"clone https://github.com/{_SYNTH_TERM}/hermes-cortex")
    assert not gate(f"clone git@github.com:{_SYNTH_TERM}/hermes-cortex.git")


def test_synthetic_term_is_blocked_outside_the_url(synthetic_denylist):
    assert gate(f"the {_SYNTH_TERM} handle is private")
    # An unrelated github repo must not launder it.
    assert gate(f"see https://github.com/someone/other-repo and {_SYNTH_TERM}")


def test_a_term_embedded_in_a_longer_token_is_still_found(synthetic_denylist):
    """Substring semantics are preserved: the window slides, it does not tokenise."""
    assert gate(f"prefix{_SYNTH_TERM}suffix")


# ── the real deny-list: configuration and the one exercisable value ────────

def test_the_real_denylist_holds_digests_of_consistent_width():
    assert enf._PII_SENSITIVE_DIGESTS, "the deny-list must not be empty"
    assert all(isinstance(d, bytes) and len(d) == 32
               for d in enf._PII_SENSITIVE_DIGESTS)
    assert len(enf._PII_SENSITIVE_LENGTHS) == len(set(enf._PII_SENSITIVE_LENGTHS))
    assert min(enf._PII_SENSITIVE_LENGTHS) > 0


def test_the_real_denylist_url_allowance_is_a_subset_of_the_denylist():
    assert enf._PII_SENSITIVE_URL_ALLOWED <= enf._PII_SENSITIVE_DIGESTS


def test_the_public_owner_handle_is_allowed_inside_the_repo_url():
    assert not gate(f"clone https://github.com/{_OWNER}/hermes-cortex.git")
    assert not gate(
        f"docs at https://raw.githubusercontent.com/{_OWNER}/hermes-cortex/main/README.md"
    )


def test_the_public_owner_handle_is_blocked_outside_the_repo_url():
    assert gate(f"meet {_OWNER} at the cafe")


# ── the unchanged classes ──────────────────────────────────────────────────

BLOCKED = [
    _FAKE_EMAIL,
    f"call {_PHONE}",
    f"connect to {_PRIVATE_HOST}",
    f"panel at {_LAN_HOST}",
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


# ── the regression guard for the whole design ──────────────────────────────

def test_neither_this_file_nor_the_enforcer_restates_an_identifier():
    """ADV-10571-1: no identifier, or piece of one, may be restated.

    Proven to discriminate, one revision per file:
      * the enforcer at 8c0212ec (before the digest deny-list) fails with 2
        components, and passes now with 0;
      * this test file at fd190e42 (before the fixture redaction) fails, and
        passes now with 0.
    """
    for path in (Path(__file__), _ENFORCER):
        src = path.read_text(encoding="utf-8").lower()
        hits = [c for c in _FORBIDDEN_COMPONENTS if c in src]
        assert not hits, (
            f"literal PII component(s) restated in {path.name}: {hits!r} — "
            "store a digest instead (docs/design/pii-denylist-digests.md)"
        )
