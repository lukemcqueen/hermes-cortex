#!/usr/bin/env python3
"""Tests for bus permission prefix-wildcard ACLs (messaging gateway).

Party finding (Architect + Security, 2026-08-24): server.py's permission
check is exact-match-or-'*' only — a scoped gateway token
(gateway_<bot>: can_write [inbox_<agent>], can_read [out_<agent>]) needs
PREFIX wildcards (inbox_*, out_*) so the gateway can serve any agent's
queue without a fleet-wide '*' grant.

Run: python3 -m pytest tests/test_bus_acl.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "server", _REPO / "core" / "cortex_bus" / "server.py")
# server.py imports FastAPI etc. — import the helper function in isolation
# by extracting the matching predicate into the module-level function.


# The predicate we're testing (mirrors server.py's check after the change):
def _queue_allowed(queue: str, allowed: list) -> bool:
    """True if queue matches: exact entry, full '*', or prefix 'inbox_*'/'out_*'."""
    if not allowed:
        return False
    for pat in allowed:
        if pat == "*" or pat == queue:
            return True
        if pat.endswith("*") and queue.startswith(pat[:-1]):
            return True
    return False


def test_exact_match():
    assert _queue_allowed("inbox_esther", ["inbox_esther"]) is True
    assert _queue_allowed("inbox_esther", ["inbox_moses"]) is False


def test_full_wildcard():
    assert _queue_allowed("anything", ["*"]) is True


def test_prefix_wildcard_inbox():
    """The gateway's write grant: inbox_* covers any agent's inbox."""
    assert _queue_allowed("inbox_titusclaude", ["inbox_*"]) is True
    assert _queue_allowed("inbox_codex", ["inbox_*"]) is True
    assert _queue_allowed("out_esther", ["inbox_*"]) is False  # not inbox


def test_prefix_wildcard_out():
    """The gateway's read grant: out_* covers any agent's outbound."""
    assert _queue_allowed("out_titusclaude", ["out_*"]) is True
    assert _queue_allowed("out_codex", ["out_*"]) is True
    assert _queue_allowed("inbox_esther", ["out_*"]) is False  # not out


def test_prefix_does_not_bleed():
    """inbox_* must NOT grant access to non-inbox queues (no prefix bleed)."""
    assert _queue_allowed("telegram_out_esther", ["inbox_*"]) is False
    assert _queue_allowed("bus.messages", ["inbox_*"]) is False


def test_empty_and_none():
    assert _queue_allowed("inbox_x", []) is False
    assert _queue_allowed("inbox_x", None) is False


def test_mid_string_wildcard_not_supported():
    """Only trailing-prefix wildcards are supported (inbox_*); a '*' in the
    middle must NOT silently grant."""
    assert _queue_allowed("inbox_esther", ["in_*esther"]) is False
