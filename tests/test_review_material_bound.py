#!/usr/bin/env python3
"""The review material's diff bound: HEAD+TAIL, and the cut must be disclosed.

Cycle 10488's close was refused with findings claiming the daemon implementation and its
tests were missing from the material. They were not missing — the gate's diff bound was
head-only while its comment claimed head+tail, so a large implementation diff was cut
mid-line ("A turn is IN FLI..."). An adversarial reviewer reading that material correctly
reported the evidence as absent. This test pins the bound itself: the tail survives, the
omission is disclosed with true numbers, and the files in the cut are named.

Run: python3 -m pytest tests/test_review_material_bound.py -q -s
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_bound",
                                               REPO / "mcp-servers" / "loop-gov-mcp.py")
assert _spec and _spec.loader, "cannot load the gate module"
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# Do not write into the production governance log (same discipline as the other gate tests).
_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)
_gate_log.propagate = False


def _diff(files: int, body_lines: int = 40) -> str:
    out = []
    for i in range(files):
        out.append(f"diff --git a/file{i}.py b/file{i}.py")
        out.append(f"--- a/file{i}.py")
        out.append(f"+++ b/file{i}.py")
        out.append(f"@@ -1,{body_lines} +1,{body_lines} @@")
        out += [f"+ added line {n} of file{i}" for n in range(body_lines)]
    return "\n".join(out) + "\n"


def test_short_diff_is_returned_unchanged():
    small = _diff(1, 3)
    assert mcp._bound_diff(small, budget=100000) == small, "a diff within budget must be untouched"
    print("  short diff passes through unchanged ✓")


def test_the_tail_survives_the_bound():
    """The actual defect: the old code kept only the head and dropped the tail."""
    big = _diff(20, 40)
    budget = 2000
    got = mcp._bound_diff(big, budget=budget)
    assert got.startswith(big[:100]), "the head must be preserved"
    assert got.rstrip().endswith(big.rstrip()[-200:]), \
        "THE TAIL MUST SURVIVE — a head-only cut is what made the reviewer report evidence missing"
    # control: reproduce the old behaviour and show it loses the tail
    old = big[:budget] + "\n...[diff truncated]...\n"
    assert not old.rstrip().endswith(big.rstrip()[-200:]), "control: the old form loses the tail"
    print(f"  head+tail bound ✓ (tail preserved); control shows the old head-only form lost it")


def test_the_omission_is_disclosed_with_true_numbers():
    big = _diff(20, 40)
    budget = 2000
    got = mcp._bound_diff(big, budget=budget)
    assert "TRUNCATED BY THE GATE'S OWN" in got
    assert "MATERIAL LIMIT, not absent evidence" in got, \
        "the notice must say the cut is the gate's limit, not missing evidence"
    head = budget * 2 // 3
    tail = budget - head
    expected_omitted = len(big) - head - tail
    assert f"{expected_omitted} of {len(big)} chars omitted" in got, \
        f"the notice must carry TRUE numbers (expected {expected_omitted} of {len(big)})"
    print(f"  disclosure: {expected_omitted} of {len(big)} chars omitted, "
          f"stated as a gate limit ✓")


def test_the_files_in_the_cut_are_named():
    big = _diff(20, 40)
    got = mcp._bound_diff(big, budget=2000)
    assert "files partly hidden in the omitted middle:" in got
    named = [f"file{i}.py" for i in range(20) if f"file{i}.py" in got]
    assert named, "at least some of the hidden files must be named"
    print(f"  files in the cut are named ({len(named)} of 20) ✓")


def test_the_gate_actually_uses_the_helper():
    """Regression guard: a bare slice would silently reintroduce the head-only bug."""
    src = (REPO / "mcp-servers" / "loop-gov-mcp.py").read_text()
    assert "_bound_diff(diff_text)" in src, "the gate must bound the diff via _bound_diff()"
    assert "diff_text[:DIFF_CHAR_BUDGET]" not in src, \
        "a bare head-only slice is the bug this test exists to prevent"
    assert "...[diff truncated]..." not in src, "the old silent marker must be gone"
    print("  gate uses _bound_diff; no bare head-only slice remains ✓")
