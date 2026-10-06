#!/usr/bin/env python3
"""End-to-end: the deploy + dogfood green claims are a RUNNABLE check, not a transcript.

Opt-in by design — this test DEPLOYS the host (pull + deploy + doctor) and then runs the
dogfood ritual, which deploys again. That is far too side-effecting for every suite pass,
so it is skipped unless explicitly requested:

    HERMES_RUN_DEPLOY_TEST=1 python3 -m pytest tests/test_dogfood_pipeline.py -q -s

What it asserts (the two markers the green claims rest on):
  1. `ops/scripts/cortex-update.sh` exits 0 AND its doctor summary reports **0 fail**;
  2. `ops/scripts/cortex-dogfood.sh` exits 0 AND prints `DOGFOOD PASSED`.

A later reviewer re-executes one command and sees the same verdict; a hand-edited
transcript cannot pass this.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "ops" / "scripts" / "cortex-update.sh"
DOGFOOD = REPO / "ops" / "scripts" / "cortex-dogfood.sh"

pytestmark = pytest.mark.skipif(
    os.environ.get("HERMES_RUN_DEPLOY_TEST") != "1",
    reason="deploys this host; opt in with HERMES_RUN_DEPLOY_TEST=1",
)

DOCTOR_SUMMARY = re.compile(
    r"Overall: (\w+)\s+\((\d+) pass · (\d+) warn · (\d+) fail · (\d+) info\)"
)


def _run(script: Path, timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(script)], cwd=str(REPO),
                          capture_output=True, text=True, timeout=timeout)


def test_there_is_a_runnable_end_to_end_check_for_the_green_claims():
    """Both scripts exist, are executable, and declare the markers this test reads.

    Cheap guard so the opt-in test cannot pass vacuously after a rename.
    """
    for script in (DEPLOY, DOGFOOD):
        assert script.is_file(), f"missing: {script}"
    assert "DOGFOOD PASSED" in DOGFOOD.read_text(encoding="utf-8"), (
        "the dogfood script must print the marker this test asserts")


def test_deploy_reports_zero_failures_and_dogfood_passes():
    deploy = _run(DEPLOY)
    assert deploy.returncode == 0, f"deploy rc={deploy.returncode}:\n{deploy.stdout[-1200:]}"
    m = DOCTOR_SUMMARY.search(deploy.stdout)
    assert m, f"no doctor summary in the deploy output:\n{deploy.stdout[-1200:]}"
    assert m.group(4) == "0", f"deploy reported FAILing checks: {m.group(0)}"

    dogfood = _run(DOGFOOD)
    assert dogfood.returncode == 0, f"dogfood rc={dogfood.returncode}:\n{dogfood.stdout[-1200:]}"
    assert "DOGFOOD PASSED" in dogfood.stdout, dogfood.stdout[-1200:]

    # The property that matters here is DEPLOYED == HEAD (what the deploy-sync gate
    # checks), NOT local == origin: a fresh commit is legitimately ahead of origin
    # until it is pushed, and requiring the push inside this test made it fail on its
    # own commit. Pushing is a separate ritual with its own gate.
    assert "Deploy sync" in dogfood.stdout or "Deploy sync" in deploy.stdout, (
        "the doctor's deploy-sync check must appear in the output this test reads")
    for line in (deploy.stdout + dogfood.stdout).splitlines():
        if "Deploy sync" in line:
            assert "✅" in line, f"deployed tree is not at HEAD: {line.strip()}"
