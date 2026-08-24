#!/usr/bin/env python3
"""Tests for the doctor's deployed-gate smoke check.

2026-08-24 blunder: the deployed adversarial-verify.py silently lost its
TOON check because its lib path resolved to a non-existent dir and the
except:pass swallowed the import error. The doctor had NO visibility —
checksums passed (deploy header only), tests passed (repo layout), the
gate was dead in production.

The smoke check must FAIL when the deployed verifier cannot resolve its
lib module, so this class of repo-works/deployed-broken can never ship
silently again.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
MANAGE = REPO_ROOT / "ops" / "scripts" / "manage"


def _load_package():
    """Load the cortex_doctor package via its parent dir (like the CLI)."""
    sys.path.insert(0, str(MANAGE))
    import cortex_doctor.checks as checks
    import cortex_doctor.results as results
    return checks, results


def _find_result(res, name):
    for r in res.checks:
        if r.get("name") == name:
            return r
    return None


def test_deployed_verifier_toon_resolution_passes_when_working():
    """With a valid deployed verifier (lib resolvable), the smoke check passes."""
    checks, results = _load_package()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        scripts = home / "scripts"
        lib = scripts / "lib"
        lib.mkdir(parents=True)
        verifier_src = REPO_ROOT / "ops" / "scripts" / "quality" / "adversarial-verify.py"
        (scripts / "adversarial-verify.py").write_text(verifier_src.read_text())
        toon_src = REPO_ROOT / "ops" / "scripts" / "lib" / "toon_parse.py"
        (lib / "toon_parse.py").write_text(toon_src.read_text())

        old_home = checks.CORTEX_HOME
        checks.CORTEX_HOME = home
        try:
            res = results.Results()
            checks.check_deployed_gate_smoke(res)
            entry = _find_result(res, "Deployed gate smoke")
            assert entry is not None, "check did not run"
            assert entry["status"] != "FAIL", f"working deployed gate flagged: {entry}"
        finally:
            checks.CORTEX_HOME = old_home


def test_deployed_verifier_toon_resolution_fails_when_broken():
    """Deployed verifier WITHOUT a resolvable lib must FAIL the smoke check.

    This reproduces the 2026-08-24 blunder: verifier present, lib missing →
    import fails silently → the check must surface it as FAIL (not INFO,
    not PASS), so the doctor blocks the push.
    """
    checks, results = _load_package()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        scripts = home / "scripts"
        scripts.mkdir(parents=True)
        verifier_src = REPO_ROOT / "ops" / "scripts" / "quality" / "adversarial-verify.py"
        (scripts / "adversarial-verify.py").write_text(verifier_src.read_text())
        # NO lib/ dir — the broken-deploy scenario

        old_home = checks.CORTEX_HOME
        checks.CORTEX_HOME = home
        try:
            res = results.Results()
            checks.check_deployed_gate_smoke(res)
            entry = _find_result(res, "Deployed gate smoke")
            assert entry is not None, "check did not run"
            assert entry["status"] == "FAIL", (
                f"broken deployed gate not flagged: {entry}"
            )
        finally:
            checks.CORTEX_HOME = old_home
