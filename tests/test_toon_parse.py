#!/usr/bin/env python3
"""Tests for toon_parse.py — TOON awareness for the PII/quality gates.

QA showstopper (AXI party 2026-08-24): before ANY TOON output ships,
the gates that scan agent-facing output must understand TOON — otherwise
placeholder-looking TOON rows (example.com, admin@client-domain.com,
/home/user/ paths) trip the secret-leak detector, and malformed TOON
(missing count header) slips past the verifier.

This module is the shared TOON parser both gates use. The golden fixture
(pinned in tests/fixtures/toon_golden.txt) is the reference emitter
output: lists, empty, error, truncated.
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "toon_parse", _REPO / "ops" / "scripts" / "lib" / "toon_parse.py")
MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["toon_parse"] = MOD
_SPEC.loader.exec_module(MOD)


def test_parse_valid_toon_blocks():
    """A well-formed TOON block parses into header + rows + count."""
    text = "tasks[2]{id,title,status}:\n  T-1,Set up bus auth,done\n  T-2,Wire bridge,in_progress\ncount: 2 of 10\n"
    blocks = MOD.parse_toon(text)
    assert len(blocks) == 1, blocks
    b = blocks[0]
    assert b["name"] == "tasks"
    assert b["count_shown"] == 2
    assert b["count_total"] == 10
    assert len(b["rows"]) == 2
    assert b["rows"][0] == ["T-1", "Set up bus auth", "done"]


def test_parse_golden_fixture():
    """The pinned golden file parses fully — every block + row + count."""
    golden = (_REPO / "tests" / "fixtures" / "toon_golden.txt").read_text()
    blocks = MOD.parse_toon(golden)
    assert len(blocks) == 5, [b["name"] for b in blocks]
    names = [b["name"] for b in blocks]
    assert names == ["tasks", "jobs", "empty", "errors", "truncated"]
    # empty block: header present, zero rows, count 0 of 3
    empty = blocks[2]
    assert empty["name"] == "empty" and empty["count_shown"] == 0
    assert empty["count_total"] == 3 and empty["rows"] == []


def test_missing_count_header_flagged():
    """Malformed TOON (rows but no count line) must be flagged."""
    text = "tasks[2]{id,title}:\n  T-1,hello\n  T-2,world\n"
    assert MOD.parse_toon(text) == []


def test_placeholder_rows_not_pii():
    """TOON rows containing placeholder-looking data are DATA, not PII.

    The secret-leak detector must not flag rows that are clearly TOON
    values — the header declares the schema, the count line declares the
    block complete. This is the exact false-positive the QA showstopper
    predicted.
    """
    text = (
        "contacts[1]{email,domain,path}:\n"
        "  admin@client-domain.com,example.org,/home/user/data\n"
        "count: 1 of 3\n"
    )
    blocks = MOD.parse_toon(text)
    assert len(blocks) == 1
    row = blocks[0]["rows"][0]
    assert row[0] == "admin@client-domain.com"  # value preserved as data
    # And the block's content is explicitly NOT a free-text PII scan target:
    assert MOD.is_toon_block(blocks[0]) is True
