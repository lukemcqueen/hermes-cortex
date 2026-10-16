#!/usr/bin/env python3
"""The pi write gate must be EXECUTED, not grepped.

Companion to `ops/install/harnesses/pi/verify-governance-extension.mjs`. That
script drives the real extension; this file makes the driving re-runnable by
anyone, and — the part that matters — asserts the driver DISCRIMINATES: pointed
at a broken gate it must FAIL.

Why a separate test rather than trusting the verifier's own green run: a guard
that has never failed on the broken artifact is a happy path, not a guard. The
second test writes the broken gate (the pre-fix shape: a `tool_call` handler
that never blocks) and requires a non-zero exit whose reason is a failed
ASSERTION — not a load error, which would "fail" for the wrong reason and prove
nothing.

Run:  python3 tests/test_pi_governance_gate.py
   or: pytest tests/test_pi_governance_gate.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERIFIER = REPO / "ops" / "install" / "harnesses" / "pi" / "verify-governance-extension.mjs"
EXTENSION = REPO / "ops" / "install" / "harnesses" / "pi" / "extensions" / "cortex-governance.ts"

# The pre-fix shape: it loads, it registers a `tool_call` handler — it just
# never blocks. A grep-based guard passes this; the verifier must not.
BROKEN = """\
export default function (pi: any) {
  pi.on("tool_call", async () => {
    return; // every write sails through — no governance consulted
  });
}
"""


def _run(node: str, env_extra: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [node, str(VERIFIER)],
        capture_output=True, text=True, env=env, timeout=300,
    )


def _node() -> str | None:
    return shutil.which("node")


def test_the_gate_is_executed_and_correct(tmp_path):
    """The real extension, driven: writes gated, reads lock-free, fail closed."""
    node = _node()
    if node is None:
        print("SKIP: node is not installed — cannot drive a TypeScript extension")
        return
    proc = _run(node, {})
    out = proc.stdout + proc.stderr
    # A host whose pi is a binary/mise install has no jiti loader: the verifier
    # reports EXTENSION SKIPPED and exits 0. That is an environment SKIP, not a
    # pass on the gate — say so rather than counting it as coverage.
    if "EXTENSION SKIPPED" in out:
        print("SKIP: this host's pi ships no jiti loader (binary/mise install)")
        return
    assert proc.returncode == 0, f"verifier failed:\n{out}"
    assert "GOVERNANCE GATE OK" in out, out
    # The ADV-1 class: write commands with no shell metacharacter. A gate that
    # classified by syntax let every one of these through. Match on the command
    # NAME so the check does not break when the verifier's fixture paths change.
    for cmd in ("cp ", "mv ", "rm ", "tee ", "dd ", "mkdir ", "touch "):
        assert f"blocked: `{cmd}" in out, f"the verifier does not cover `{cmd}...`:\n{out}"
    # And read-only must NOT be gated, or the gate is friction without security.
    assert "read-only bash stays lock-free" in out, out
    # The block must name the live lock that does NOT cover this repo — the
    # check exists in the verifier and must keep running.
    assert "the refusal names the locks that do NOT cover this repo" in out, out


def test_the_verifier_discriminates_on_the_named_lock_section(tmp_path):
    """A gate that blocks but names nothing must FAIL the verifier.

    The discrimination seam is the REAL extension with exactly the rendering
    line removed — the mutation the report is about (a refusal that says "no
    lock covers this repo" while a live lock sits beside it, unnamed).
    """
    node = _node()
    if node is None:
        print("SKIP: node is not installed")
        return
    source = EXTENSION.read_text()
    spread = "    ...foreignLockSection(detail),\n"
    assert spread in source, (
        "the mutation target is gone — update this test rather than letting it "
        "mutate nothing and pass"
    )
    mutant = tmp_path / "no-named-locks.ts"
    mutant.write_text(source.replace(spread, ""))
    proc = _run(node, {"PI_GOV_EXT": str(mutant)})
    out = proc.stdout + proc.stderr
    if "EXTENSION SKIPPED" in out:
        print("SKIP: this host's pi ships no jiti loader")
        return
    assert proc.returncode != 0, (
        "the verifier PASSED a gate whose refusal names no lock — the named-lock "
        f"check is a happy path:\n{out}"
    )
    assert "failed to LOAD" not in out, f"the mutant did not even load:\n{out}"
    assert "the refusal names the locks that do NOT cover this repo" in out, out


def test_the_verifier_discriminates(tmp_path):
    """Pointed at a broken gate, the verifier MUST fail — on an assertion."""
    node = _node()
    if node is None:
        print("SKIP: node is not installed")
        return
    broken = tmp_path / "broken-gate.ts"
    broken.write_text(BROKEN)
    proc = _run(node, {"PI_GOV_EXT": str(broken)})
    out = proc.stdout + proc.stderr
    if "EXTENSION SKIPPED" in out:
        print("SKIP: this host's pi ships no jiti loader")
        return
    assert proc.returncode != 0, (
        "the verifier PASSED a gate that blocks nothing — it is a happy path, "
        f"not a guard:\n{out}"
    )
    # Fail for the RIGHT reason: the broken gate must LOAD (so the assertions
    # run) and then fail them. A load error would also be non-zero and would
    # prove nothing about the assertions.
    assert "failed to LOAD" not in out, f"the broken gate did not even load:\n{out}"
    assert "GOVERNANCE GATE BROKEN" in out, out
    assert "NO lock => write BLOCKED" in out, out


if __name__ == "__main__":
    import tempfile

    failures = 0
    for fn in (
        test_the_gate_is_executed_and_correct,
        test_the_verifier_discriminates,
        test_the_verifier_discriminates_on_the_named_lock_section,
    ):
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
    sys.exit(1 if failures else 0)
