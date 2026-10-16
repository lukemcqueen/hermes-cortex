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
_PHONE_INTL = "+" + "82" + " " + "10-" + "1234" + "-5678"
_PRIVATE_HOST = "https" + "://my-secret-server" + ".internal:8443"
_LAN_HOST = "https" + "://192.168." + "1.10/admin"

# NOT phones, but the pre-2026-10-14 pattern flagged them: it ended with an
# OPTIONAL single separator between a three-to-four digit group and a four digit
# group, so two four-digit groups joined by one dash matched. These are the real
# shapes that blocked a legitimate plan write and the evidence transcript.
# Assembled from parts and with every long digit run SPLIT, so this file carries
# no literal the gate it is testing would block (Rule: a scanner that scans its
# own source cannot restate its fixtures).
_DASH = "-"
_LINE_RANGE = "5341" + _DASH + "5377"
_SESSION_KEY = "20" + "26" + "10" + "14" + "_" + "195745" + "_" + "cd0e365b"
_VERSION_PAIR = "v1.2.0" + _DASH + "20" + "26" + "10" + "14"
_EPOCH_RANGE = "12000" + _DASH + "16000"


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
    f"ring {_PHONE_INTL}",
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
    # two four-digit groups joined by ONE dash are not a phone number — the
    # shapes that used to be blocked (see the differential test below).
    f"lines {_LINE_RANGE}",
    f"session {_SESSION_KEY}",
    f"tag {_VERSION_PAIR}",
    f"budget {_EPOCH_RANGE} tokens",
]


@pytest.mark.parametrize("text", BLOCKED)
def test_pii_blocked(text):
    assert gate(text), f"should have blocked: {text[:50]}"


@pytest.mark.parametrize("text", ALLOWED)
def test_non_pii_allowed(text):
    assert not gate(text), f"should NOT have blocked: {text[:50]}"


# ── the phone narrowing, pinned to the revision it replaced ────────────────

# The enforcer revision BEFORE the phone narrowing, pinned by SHA — never 'HEAD':
# the fix is committed in the same change as this test, so HEAD would resolve to
# the FIXED module and the before/after comparison would be a tautology.
_PRE_NARROWING_REV = "31699baa"


def _load_enforcer_at(rev):
    """Extract the enforcer at <rev> and load it; None when it cannot be read.

    'Could not verify' is its own outcome — the caller SKIPS loudly rather than
    letting an unreadable revision read as a passing comparison.
    """
    import subprocess
    import tempfile

    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO), "show",
             f"{rev}:plugins/governance-enforcer/__init__.py"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    path = Path(tempfile.mkdtemp()) / "enforcer_at_rev.py"
    path.write_text(out.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("enforcer_at_rev", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_phone_narrowing_drops_the_false_positives_and_keeps_phones():
    """Asserted against the revision that HAD the bug, not against a claim."""
    prev = _load_enforcer_at(_PRE_NARROWING_REV)
    if prev is None:
        pytest.skip(
            f"could not extract {_PRE_NARROWING_REV} — the before/after cannot be "
            "verified here, so this is NOT a pass"
        )

    non_phones = [
        _LINE_RANGE,
        _SESSION_KEY,
        _VERSION_PAIR,
        _EPOCH_RANGE,
        f"lines {_LINE_RANGE}, more {_EPOCH_RANGE}",
    ]

    # 1. The baseline must REPRODUCE the bug, or the comparison below proves
    #    nothing. A baseline that already passes is the tautology trap.
    reproduced = [s for s in non_phones if prev._PII_PHONE_RE.search(s)]
    assert len(reproduced) >= 3, (
        "the pre-narrowing revision does not reproduce the false positives this "
        f"change removes ({len(reproduced)}/{len(non_phones)}) — the comparison "
        "would be vacuous"
    )

    # 2. The fix drops them...
    still = [s for s in non_phones if enf._PII_PHONE_RE.search(s)]
    assert not still, f"still treated as phones after the narrowing: {still}"

    # 3. ...while real phone formats fire in BOTH revisions.
    for p in (_PHONE, _PHONE_INTL):
        assert prev._PII_PHONE_RE.search(p), f"baseline did not match a phone: {p}"
        assert enf._PII_PHONE_RE.search(p), f"the narrowing lost a phone: {p}"


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


# ── a UUID is an identifier, not a phone number (2026-10-17) ───────────────

# Measured defect: the two-separator national form can align to the TAIL of one
# hex group plus the two groups after it, so a canonical UUID is refused by the
# write gate as a "phone number". Sampled against the pre-fix pattern over
# 200,000 v4 UUIDs: 4,749 (2.37%) were flagged, e.g. the tail of the first hex
# group plus the next two. It refused a verbatim psql row in
# docs/evidence/backlog-run-2026-10-16-selection.md, which had to be elided.
#
# The fixtures below are real UUIDs the pre-fix pattern DID flag, assembled from
# parts so this file never restates a dash-joined digit run: the gate scans the
# file it is written into, and a restated example is refused exactly as the data
# was (Rule 24 in enforcement-change-safety).
_UUID_HITS = [
    "450062e8" + _DASH + "de60" + _DASH + "4647" + _DASH + "9420" + _DASH
    + "2fbfb466bfa9",
    "e4cd1f80" + _DASH + "8024" + _DASH + "4072" + _DASH + "86c3" + _DASH
    + "307c5bbf1d77",
    "11022c1f" + _DASH + "8e82" + _DASH + "4732" + _DASH + "8227" + _DASH
    + "c410c045dea3",
    "363a3f09" + _DASH + "5145" + _DASH + "4166" + _DASH + "be2c" + _DASH
    + "4cde5fb0dae7",
    "f027bb8e" + _DASH + "1810" + _DASH + "4515" + _DASH + "9302" + _DASH
    + "e199314742bc",
]


def test_a_canonical_uuid_is_not_treated_as_a_phone_number():
    for u in _UUID_HITS:
        assert not gate(f"session {u} ran the check"), (
            f"a UUID was refused as a phone number: {u}")


def test_random_uuid_samples_are_never_flagged():
    """Property, not a single example: no canonical UUID is refused."""
    import uuid as _uuid

    samples = [str(_uuid.uuid4()) for _ in range(2000)]
    flagged = [u for u in samples if gate(f"row {u}")]
    assert not flagged, f"UUIDs refused as phone numbers: {flagged[:3]}"


def test_a_dashed_digit_run_that_is_not_a_uuid_still_fires():
    """No coverage is silently dropped: the phone shape itself still matches.

    The narrowing is scoped to UUID tokens. A dash-joined run of digit groups
    that is NOT a UUID keeps being reported, because nothing distinguishes it
    from a formatted number.
    """
    assert gate("acct " + "1234" + _DASH + "5678" + _DASH + "9012")


# The revision BEFORE this change, pinned by SHA — never 'HEAD': the fix lands
# in the same change as this test, so HEAD would resolve to the FIXED module and
# the comparison would be a tautology.
_PRE_UUID_FIX_REV = "4764289b"


def test_the_uuid_false_positive_existed_before_this_change():
    """Asserted against the revision that HAD the defect, not against a claim."""
    prev = _load_enforcer_at(_PRE_UUID_FIX_REV)
    if prev is None:
        pytest.skip(
            f"could not extract {_PRE_UUID_FIX_REV} — the before/after cannot be "
            "verified here, so this is NOT a pass"
        )

    def prev_gate(text: str) -> bool:
        args = {"path": str(_REPO / "docs" / "test.md"), "content": text}
        return prev._check_pii_content_gate("write_file", args) is not None

    # 1. The baseline must REPRODUCE the defect, or the comparison proves
    #    nothing. A baseline that already passes is the tautology trap.
    reproduced = [u for u in _UUID_HITS if prev_gate(f"session {u} ran the check")]
    assert len(reproduced) >= 3, (
        "the pre-fix revision does not reproduce the UUID false positive this "
        f"change removes ({len(reproduced)}/{len(_UUID_HITS)}) — the comparison "
        "would be vacuous"
    )

    # 2. ...the fix drops every one of them...
    assert not [u for u in _UUID_HITS if gate(f"session {u} ran the check")], (
        "a UUID is still refused as a phone number after the fix")

    # 3. ...while real phone formats fire in BOTH revisions.
    for p in (f"call {_PHONE}", f"ring {_PHONE_INTL}"):
        assert prev_gate(p), f"baseline did not match a phone: {p}"
        assert gate(p), f"the narrowing lost a phone: {p}"
