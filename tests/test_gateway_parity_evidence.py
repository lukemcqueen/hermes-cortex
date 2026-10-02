#!/usr/bin/env python3
"""Re-executable evidence for the gateway parity claims (review findings ADV-10482-*).

Came out of an adversarial review that refused the close: the worker's note claimed
"111 gateway tests pass" and "the gap register went 9 -> 3", but neither number was
traceable to COMMITTED material — the only proof lived in a terminal transcript. Per the
constitution's remedy for an unverified claim, the proof is committed as something a
later reviewer can RE-RUN rather than re-read: this file executes the gateway suites and
asserts the numbers, so the evidence regenerates instead of going stale.

Run (this is the evidence):
    python3 -m pytest tests/test_gateway_parity_evidence.py -q -s
"""
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# The suites whose combined count the parity claim rests on.
_SUITES = [
    "tests/test_cortex_gateway_transport.py",
    "tests/test_cortex_gateway_daemon.py",
    "tests/test_cortex_gateway_backend.py",
    "tests/test_cortex_gateway_key_guard.py",
    "tests/test_msg_gateway.py",
    "tests/test_gateway_envelope.py",
    "tests/test_telegram_bridge.py",
    "tests/test_telegram_bridge_e2e.py",
    "tests/test_telegram_notify_unit.py",
    "tests/test_cortex_gateway_parity_matrix.py",
    "tests/test_cortex_gateway_daemon_slice.py",
]


def test_gateway_suites_pass_and_the_count_is_reproducible():
    """The committed proof for 'N gateway tests pass': run them, assert the number."""
    r = subprocess.run([sys.executable, "-m", "pytest", *_SUITES, "-q"],
                       cwd=_REPO, capture_output=True, text=True, timeout=600)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"
    print(f"  re-executed: {' '.join(_SUITES)}")
    print(f"  pytest says: {tail}")
    m = re.search(r"(\d+) passed", r.stdout)
    assert m, f"no pytest summary in the output:\n{r.stdout[-800:]}\n{r.stderr[-400:]}"
    passed = int(m.group(1))
    assert passed >= 111, (
        f"the parity claim is >= 111 passing gateway tests; this run shows {passed}. "
        "If suites were removed, the claim in docs/design/cortex-gateway-parity.md must "
        "be corrected to the measured number.")
    assert r.returncode == 0, f"suites failed (rc={r.returncode}):\n{r.stdout[-800:]}"
    print(f"  VERIFIED: {passed} gateway tests pass (claim >= 111) ✓")


def test_gap_register_in_the_doc_is_numbered_and_matches_the_test():
    """The doc's register must be numbered 1-9 with status, so 9 -> 3 is checkable."""
    doc = (_REPO / "docs" / "design" / "cortex-gateway-parity.md").read_text()
    # the register: one row per original gap, G1..G9
    ids = re.findall(r"\bG([1-9])\b", doc)
    assert len(set(ids)) == 9, \
        f"the doc must name all nine original gaps G1..G9; found {sorted(set(ids))}"
    for gid in sorted(set(ids)):
        assert re.search(rf"\bG{gid}\b.*?(closed|OPEN)", doc, re.I | re.S), \
            f"gap G{gid} has no closed/OPEN status"
    # Count from the TABLE ROWS only (a loose lookahead counted prose mentions too and
    # printed "10 marked closed" for 6 actual rows — a false number in the evidence
    # itself, which is exactly what this file exists to prevent).
    rows = re.findall(r"^\|\s*(G[1-9])\s*\|([^\n]*)\|", doc, re.M)
    assert len({g for g, _ in rows}) == 9, f"expected 9 register rows, found {rows}"
    closed = [g for g, rest in rows if re.search(r"\|\s*closed", rest, re.I)]
    opened = [g for g, rest in rows if re.search(r"OPEN", rest)]
    print(f"  doc register rows: 9 | closed={len(closed)} {closed} | open={len(opened)} {opened}")
    assert len(closed) == 9 and len(opened) == 0, \
        f"the daemon slice closed the register; rows say closed={closed} open={opened}"


def test_correction_is_recorded_in_the_doc():
    """The media/caption claim was corrected BY execution — that must be on the record."""
    doc = (_REPO / "docs" / "design" / "cortex-gateway-parity.md").read_text().lower()
    assert "corrected" in doc or "revision" in doc, \
        "the doc must record that an earlier claim was corrected by execution"
    assert "caption" in doc, "the corrected claim was about captioned media"
    print("  doc records the execution-driven correction ✓")
