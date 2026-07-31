"""Regression tests for cleanup-commit-regression-check/find-deleted-funcs.py.

Covers the AST function-set diff that catches mass-edit passes stripping
`def` lines (2026-07-31 case: commit 84272894 broke 5 scripts; the detector
must flag single-function deletions while tolerating balanced rewrites).
"""
import importlib.util
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
PROBE = (
    REPO_ROOT
    / "skills"
    / "devops"
    / "cleanup-commit-regression-check"
    / "scripts"
    / "find-deleted-funcs.py"
)


def _load_probe():
    spec = importlib.util.spec_from_file_location("find_deleted_funcs_test", PROBE)
    assert spec is not None and spec.loader is not None, f"cannot load {PROBE}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_funcs_of_parses_functions():
    probe = _load_probe()
    src = "def keep(): pass\ndef _resolve_var():\n    return 1\nasync def main():\n    return 0\n"
    assert probe.funcs_of(src) == {"keep", "_resolve_var", "main"}


def test_funcs_of_tolerates_syntax_errors():
    probe = _load_probe()
    assert probe.funcs_of("def broken(:\n") == set()


def test_detector_flags_single_function_deletion():
    """The bug class: commit strips one def line -> orphaned body, no SyntaxError."""
    probe = _load_probe()
    parent = "def keep(): pass\ndef _resolve_var():\n    return 1\ndef main():\n    return 0\n"
    current = "def keep(): pass\ndef main():\n    return 0\n"
    deleted = probe.funcs_of(parent) - probe.funcs_of(current)
    assert deleted == {"_resolve_var"}


def test_probe_runs_against_known_regression_commit():
    """84272894 stripped def lines; 362cf70f restored them, so current tree is clean."""
    result = subprocess.run(
        [
            "python3",
            str(PROBE),
            "84272894",
            "--path-filter",
            "ops/scripts",
            "--repo",
            str(REPO_ROOT),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no function deletions detected" in result.stdout


def test_repo_default_is_portable():
    """Hardcoded /home/<user> literal was removed; env or cwd supplies the repo."""
    src = PROBE.read_text()
    assert "HERMES_CORTEX_REPO" in src
    assert '"/home/' not in src and "'/home/" not in src
