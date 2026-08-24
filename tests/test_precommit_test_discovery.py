#!/usr/bin/env python3
"""Tests for pre-commit-score monorepo test-discovery fix.

TitusClaude smoke test (2026-08-24, verified by Esther): pre-commit-score
fabricates pass-pct=100 for monorepos. It only measures when a ROOT-level
pytest.ini/setup.cfg/pyproject.toml exists AND tests live in tests/ at root.
Repos with apps/<svc>/ layout (koscap-av: tests in apps/api/tests, config in
apps/api/pyproject.toml, runner `./run test`) never trigger measurement —
every cycle scores pass-pct=100 unmeasured, inflating governance scores.

Fix (TitusClaude proposal, verified sound):
1. Per-repo opt-in: ops/scripts/test-command.sh at repo root — the repo
   declares how tests run (e.g. `./run test`). Executed if present.
2. Fallback discovery: find test configs up to depth 3 (pytest.ini,
   pyproject.toml with [tool.pytest], setup.cfg) and measure each.
3. Warn when test infra exists but measurement fails — never silent 100.
4. Keep fail-open (100) only when NO test infra exists.

Run: python3 -m pytest tests/test_precommit_test_discovery.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# Import the discovery logic (extracted to an importable module)
import ops.scripts.precommit_test_discovery as ptd  # noqa: E402


# ── Discovery tests ──────────────────────────────────────────

def test_finds_nested_pyproject(tmp_path):
    """A pyproject.toml at apps/api/ (depth 2) is discovered."""
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    dirs = ptd.discover_test_dirs(str(tmp_path), max_depth=3)
    assert (tmp_path / "apps" / "api") in dirs


def test_finds_nested_pytest_ini(tmp_path):
    (tmp_path / "services" / "auth" / "tests").mkdir(parents=True)
    (tmp_path / "services" / "auth" / "pytest.ini").write_text("[pytest]\n")
    dirs = ptd.discover_test_dirs(str(tmp_path), max_depth=3)
    assert (tmp_path / "services" / "auth") in dirs


def test_ignores_pyproject_without_pytest_tool(tmp_path):
    """A pyproject.toml without [tool.pytest] is NOT a test config."""
    (tmp_path / "apps" / "web").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "pyproject.toml").write_text("[build-system]\n")
    dirs = ptd.discover_test_dirs(str(tmp_path), max_depth=3)
    assert (tmp_path / "apps" / "web") not in dirs


def test_respects_max_depth(tmp_path):
    """A config at depth 4 (beyond max_depth=3) is NOT discovered."""
    (tmp_path / "a" / "b" / "c" / "d").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c" / "d" / "pytest.ini").write_text("[pytest]\n")
    dirs = ptd.discover_test_dirs(str(tmp_path), max_depth=3)
    assert not dirs


# ── Test-command opt-in tests ────────────────────────────────

def test_test_command_script_used_when_present(tmp_path):
    """ops/scripts/test-command.sh at repo root is preferred over discovery."""
    scripts = tmp_path / "ops" / "scripts"
    scripts.mkdir(parents=True)
    tc = scripts / "test-command.sh"
    tc.write_text("#!/usr/bin/env bash\necho '7 passed'\n")
    tc.chmod(0o755)
    cmd = ptd.resolve_test_command(str(tmp_path))
    assert cmd is not None
    assert "test-command.sh" in cmd


def test_test_command_absent_falls_back_to_discovery(tmp_path):
    """No test-command.sh → discovery is used."""
    cmd = ptd.resolve_test_command(str(tmp_path))
    assert cmd is None  # falls through to discovery path


# ── Measurement tests ────────────────────────────────────────

def test_measure_pass_pct_from_output():
    assert ptd.parse_pass_pct("8 passed, 2 failed in 0.3s") == 80
    assert ptd.parse_pass_pct("10 passed in 0.1s") == 100
    assert ptd.parse_pass_pct("5 failed in 0.2s") == 0


def test_parse_pass_pct_counts_errors_as_failures():
    """TitusClaude finding (verified): 'N passed, M errors' scored 100."""
    assert ptd.parse_pass_pct("598 passed, 69 warnings, 15 errors in 13.38s") == 98
    assert ptd.parse_pass_pct("612 passed in 10.5s") == 100
    assert ptd.parse_pass_pct("598 passed, 14 failed in 13.38s") == 98


def test_parse_pass_pct_errors_only_is_zero():
    """No passed token but errors present → 0, never None (silent 100)."""
    assert ptd.parse_pass_pct("3 errors in 0.2s") == 0


def test_parse_pass_pct_no_summary_is_none():
    """Unparseable output → None (caller warns; never silent 100)."""
    assert ptd.parse_pass_pct("random output without summary") is None


def test_no_test_infra_is_fail_open():
    """No test configs found → pass_pct stays 100 (fail-open), no warning."""
    assert ptd.classify_measurement(100, found_infra=False, warned=False) == {
        "pass_pct": 100, "warned": False}


def test_infra_present_but_measurement_failed_warns():
    """Test infra exists but pytest output unparseable → warn, not silent 100."""
    result = ptd.classify_measurement(100, found_infra=True, warned=True)
    assert result["warned"] is True
    assert result["pass_pct"] == 100  # fail-open but flagged
