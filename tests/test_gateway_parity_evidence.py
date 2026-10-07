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

# The WHOLE gateway test surface, recorded next to the parity count because they are
# different numbers serving different claims. A review finding (2026-10-07) read the
# parity file's "126 passed" as the total while the full surface was 243 — a reader
# cannot tell the scope from the number, so the file now states both, measured.
_SURFACE = [
    "tests/test_cortex_gateway_backend.py",
    "tests/test_cortex_gateway_daemon.py",
    "tests/test_cortex_gateway_daemon_slice.py",
    "tests/test_cortex_gateway_key_guard.py",
    "tests/test_cortex_gateway_parity_matrix.py",
    "tests/test_cortex_gateway_systemd.py",
    "tests/test_cortex_gateway_telegram_env.py",
    "tests/test_cortex_gateway_transport.py",
    "tests/test_gateway_agent_registry.py",
    "tests/test_gateway_approvals.py",
    "tests/test_gateway_bus_shapes.py",
    "tests/test_gateway_cutover_guards.py",
    "tests/test_gateway_dispatch_failure_visible.py",
    "tests/test_gateway_envelope.py",
    "tests/test_gateway_modules_are_deployed.py",
    "tests/test_gateway_new_session.py",
    "tests/test_gateway_pairing.py",
    "tests/test_gateway_streaming.py",
    "tests/test_gateway_typing.py",
    "tests/test_msg_gateway.py",
    "tests/test_pi_reply_path_boundaries.py",
    "tests/test_telegram_bridge.py",
    "tests/test_telegram_bridge_e2e.py",
    "tests/test_telegram_notify_unit.py",
]


def test_gateway_suites_pass_and_the_count_is_reproducible():
    """The committed proof for 'N gateway tests pass': run them, assert the number.

    Also WRITES the run output to docs/evidence/gateway-suite-results.txt. An
    adversarial review asked for exactly this (ADV-10488-2/-3: "commit the regression
    run output as a file ... so a later reviewer can re-execute and verify") — a claim
    whose only support is a terminal transcript is unverifiable the moment the
    transcript is gone, and a truncated review material cannot carry it either.
    """
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

    # The FULL gateway surface, measured here too. Two different numbers serve two
    # different claims, and a reader cannot tell them apart from the figure alone.
    rs = subprocess.run([sys.executable, "-m", "pytest", *_SURFACE, "-q"],
                        cwd=_REPO, capture_output=True, text=True, timeout=900)
    assert rs.returncode == 0, \
        f"the full gateway surface failed (rc={rs.returncode}):\n{rs.stdout[-900:]}"
    ms = re.search(r"(\d+) passed", rs.stdout)
    assert ms, f"the full-surface run produced no pytest summary:\n{rs.stdout[-900:]}"
    surface_passed = int(ms.group(1))
    surface_tail = (rs.stdout.strip().splitlines()[-1]
                    if rs.stdout.strip() else "(no output)")
    assert surface_passed >= passed, (
        f"the parity suites report {passed} tests but the whole surface reports "
        f"{surface_passed} — the two lists have drifted apart; fix _SURFACE/_SUITES")
    print(f"  VERIFIED: whole gateway surface {surface_passed} passed "
          f"(parity suites {passed}) ✓")

    # Commit the evidence, so the claim survives the transcript and the material bound.
    evidence = _REPO / "docs" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    out = evidence / "gateway-suite-results.txt"
    # Host paths are scrubbed: this file is committed to a PUBLIC repo, and a captured
    # pytest `rootdir: /home/<user>/...` line is a PII finding in the pre-commit scan.
    def _scrub(text: str) -> str:
        return re.sub(r"/home/[A-Za-z0-9._-]+", "$HOME", text)

    out.write_text(
        "Gateway suite results — regenerated by tests/test_gateway_parity_evidence.py.\n"
        "Run it and this file is rewritten from the actual output:\n"
        "    python3 -m pytest tests/test_gateway_parity_evidence.py -q -s\n\n"
        f"SCOPE — the {len(_SUITES)} suites listed first are the PARITY tests the cutover\n"
        f"claim (>= 111) rests on. The whole gateway surface is {len(_SURFACE)} files and\n"
        f"{surface_passed} tests: cite THAT number for gateway coverage, and this one for\n"
        "the parity claim. Both are measured in the same run of this file.\n\n"
        f"parity suites ({len(_SUITES)}):\n" + "\n".join(f"  {s}" for s in _SUITES) + "\n\n"
        f"measured: {passed} passed (parity claim, not the surface total)\n"
        f"pytest summary: {_scrub(tail)}\n\n"
        f"whole gateway surface ({len(_SURFACE)} files):\n"
        + "\n".join(f"  {s}" for s in _SURFACE) + "\n\n"
        f"measured: {surface_passed} passed (whole gateway surface)\n"
        f"pytest summary: {_scrub(surface_tail)}\n\n"
        "Tail of the parity run (host paths scrubbed):\n" + _scrub(r.stdout[-1500:]) + "\n")
    body = out.read_text()
    assert f"{passed} passed" in body and f"{surface_passed} passed" in body, \
        "both measured numbers must appear in the evidence file"
    print(f"  evidence committed to {out.relative_to(_REPO)} ✓")

    # Also record the TEST NAMES cited in review findings. ADV-10488-1 called a
    # "5 tests" claim fabrication because the material (truncated mid-file) showed
    # only four — the fifth existed and was cut. A collected list is short, survives
    # the material bound, and is regenerated here rather than asserted by hand.
    cited = ["tests/test_review_material_bound.py", "tests/test_cortex_gateway_daemon_slice.py"]
    names = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", *cited],
                           cwd=_REPO, capture_output=True, text=True, timeout=300)
    combined = names.stdout + names.stderr
    # pytest's non-quiet collection is a TREE (<Module file> / <Function test>), not
    # node ids; `-q` prints only the summary. Build module::function pairs from the tree.
    listed, module = [], ""
    for ln in combined.splitlines():
        s = ln.strip()
        if s.startswith("<Module "):
            module = s[len("<Module "):].rstrip(">").strip()
        elif s.startswith("<Function ") and module:
            listed.append(f"{module}::{s[len('<Function '):].rstrip('>').strip()}")
    assert listed, (
        "collected no test names — refusing to write a '0 names' line into the evidence "
        f"file (that would be a false statement inside the evidence itself). Output was:\n"
        f"{combined[-400:]}")
    with open(out, "a") as fh:
        fh.write(f"\ntest names in the files cited by review findings ({len(listed)}):\n")
        fh.write("\n".join(f"  {n}" for n in listed) + "\n")
    print(f"  collected {len(listed)} test names into the evidence file ✓")


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
