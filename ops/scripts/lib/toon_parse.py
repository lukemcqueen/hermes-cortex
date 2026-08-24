#!/usr/bin/env python3
"""toon_parse.py — shared TOON parser for the PII/quality gates.

TOON (Token-Optimized Output Notation) is the fleet's agent-facing output
convention (AXI). A TOON block looks like:

    tasks[2]{id,title,status}:
      T-1,Set up bus auth,done
      T-2,Wire telegram bridge,in_progress
    count: 2 of 10

Before ANY TOON output ships, the gates that scan agent-facing output
must understand TOON — otherwise placeholder-looking TOON rows (emails,
domains, home paths as DATA values) trip the secret-leak detector, and
malformed TOON slips past the verifier. This module is the single parser
both gates use.

Block grammar (strict):
    <name>[<count_shown>]{<fields>}:
      <field>,<value>[,<value>...]      (one per row, 2-space indent)
    count: <count_shown> of <count_total>

A block is well-formed ONLY if: header present, count_shown in header
== count_shown in count line, and (rows == count_shown) or
(rows == 0 for a definitive empty block). Anything else → not TOON
(returned as []), which callers treat as malformed/needs-scanned.
"""
from __future__ import annotations

import re
from typing import Optional

_HEADER_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\[(\d+)\]\{([^}]+)\}:\s*$")
_COUNT_RE = re.compile(r"^\s*count:\s*(\d+)\s+of\s+(\d+)\s*$")
_ROW_RE = re.compile(r"^\s{2}(.+)$")


def parse_toon(text: str) -> list[dict]:
    """Parse TOON blocks from text. Returns [] when NO valid block exists.

    A block is valid only when header + count agree and row count matches.
    Malformed TOON (rows without a count line, count mismatch) is NOT a
    block — callers flag it as malformed.
    """
    blocks: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name, shown_s, fields_s = m.group(1), int(m.group(2)), m.group(3)
        fields = [f.strip() for f in fields_s.split(",")]
        j = i + 1
        rows: list[list[str]] = []
        while j < len(lines) and lines[j].strip() and not _COUNT_RE.match(lines[j]):
            rm = _ROW_RE.match(lines[j])
            if rm:
                rows.append([c.strip() for c in rm.group(1).split(",")])
            j += 1
        if j >= len(lines):
            break  # no count line — malformed, not a block
        cm = _COUNT_RE.match(lines[j])
        count_shown, count_total = int(cm.group(1)), int(cm.group(2))
        # Strict agreement: header shown == count shown, rows match shown.
        if shown_s != count_shown:
            i = j + 1
            continue
        if len(rows) != count_shown:
            i = j + 1
            continue
        blocks.append({
            "name": name,
            "fields": fields,
            "rows": rows,
            "count_shown": count_shown,
            "count_total": count_total,
        })
        i = j + 1
    return blocks


def is_toon_block(block: dict) -> bool:
    """A parsed block is by definition TOON (schema-declared data rows).

    Gate consumers use this to decide whether the block's row VALUES are
    schema data (never PII-scan targets as free text) while still
    scanning the header/count lines normally.
    """
    return bool(block) and "name" in block and "count_total" in block


def find_malformed_toon(text: str) -> Optional[str]:
    """Return a description of the FIRST malformed TOON construct, or None.

    Malformed = a TOON-looking header followed by rows but NO matching
    count line, or a count mismatch. The verifier uses this to flag
    broken TOON before it ships.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if not m:
            continue
        shown_s = int(m.group(2))
        j = i + 1
        while j < len(lines) and lines[j].strip() and not _COUNT_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            return f"line {i + 1}: TOON header '{m.group(1)}' has no count line"
        cm = _COUNT_RE.match(lines[j])
        if int(cm.group(1)) != shown_s:
            return (f"line {i + 1}: count mismatch — header [{shown_s}] "
                    f"but count says [{cm.group(1)}]")
    return None
