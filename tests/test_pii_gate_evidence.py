#!/usr/bin/env python3
"""Provenance for docs/evidence/pii-gate-redaction-evidence.txt.

The artifact is a claim about a public file, so it must be ACTUAL script
output: this test re-runs the generator in --check mode and fails when the
committed evidence no longer matches the live derivation, or when the claim it
records does not hold. A hand-written table cannot pass.
"""
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_MANAGE = _REPO / "ops" / "scripts" / "manage"
_GENERATOR = _MANAGE / "pii-gate-evidence.py"
_RUNNER = _MANAGE / "run-pii-gate-evidence.sh"
_ARTIFACT = _REPO / "docs" / "evidence" / "pii-gate-redaction-evidence.txt"


def test_the_generator_and_runner_are_both_present():
    assert _GENERATOR.is_file(), f"missing {_GENERATOR}"
    assert _RUNNER.is_file(), f"missing {_RUNNER}"


def test_the_committed_evidence_is_actual_script_output():
    proc = subprocess.run(
        [sys.executable, str(_GENERATOR), "--check"],
        cwd=str(_REPO), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_committed_artifact_records_a_pass():
    assert "**Verdict: PASS**" in _ARTIFACT.read_text(encoding="utf-8")
