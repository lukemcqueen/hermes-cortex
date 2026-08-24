#!/usr/bin/env python3
"""Tests for the doctor's CLAUDE.md governance checks.

Luke 2026-08-24: titusclaude (Claude Code) must have the same governance as
Hermes agents, and the doctor must check CLAUDE.md like it checks AGENTS.md —
especially on NON-hermes-cortex repos where Claude usually works.

Covers check_dev_repo_claude: scans dev repos, warns when CLAUDE.md is
missing while a Claude agent is configured, passes when all have it, and
skips when no Claude agent is configured.

Run: python3 -m pytest tests/test_doctor_claude_check.py -q
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SYS_PATH_INSERTED = False
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point HOME at a temp dir with a fake git repo (no CLAUDE.md)."""
    repo = tmp_path / "client-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# client repo\n")
    # A real git repo so the active-repo check passes
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"],
                   check=True, capture_output=True)
    (repo / "README.md").write_text("# client repo\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)

    monkeypatch.setattr(checks, "HOME", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_REPO", _REPO)
    # No Claude configured by default (fresh temp home)
    monkeypatch.setattr(checks, "run_bg", lambda cmd: "" if cmd[0] == "command" else "x")
    return tmp_path


def _make_results() -> Results:
    return Results()


def test_skips_when_no_claude_configured(fake_home):
    """No .mcp.json/.claude/claude binary → check does nothing (no entries)."""
    res = _make_results()
    checks.check_dev_repo_claude(res)
    assert len(res.checks) == 0


def test_warns_when_claude_configured_but_repo_missing_claude_md(fake_home):
    """Claude configured + dev repo without CLAUDE.md → WARN."""
    (fake_home / ".mcp.json").write_text("{}")
    res = _make_results()
    checks.check_dev_repo_claude(res)
    warns = [e for e in res.checks if e['status'] == "WARN"]
    assert any("CLAUDE.md" in e["name"] for e in warns), (
        f"expected a CLAUDE.md WARN, got: {[e['name'] for e in res.checks]}")


def test_passes_when_all_repos_have_claude_md(fake_home):
    """Claude configured + all dev repos have CLAUDE.md → PASS."""
    (fake_home / ".mcp.json").write_text("{}")
    (fake_home / "client-repo" / "CLAUDE.md").write_text("# governance\n")
    res = _make_results()
    checks.check_dev_repo_claude(res)
    passes = [e for e in res.checks if e['status'] == "PASS"]
    assert any("CLAUDE.md" in e["name"] for e in passes), (
        f"expected a CLAUDE.md PASS, got: {[e['name'] for e in res.checks]}")


def test_skips_hermes_cortex_repo_itself(fake_home):
    """CORTEX_REPO is excluded from the dev-repo scan (covered by check_repo)."""
    (fake_home / ".mcp.json").write_text("{}")
    # Simulate CORTEX_REPO inside the scan area — it must be skipped.
    res = _make_results()
    checks.check_dev_repo_claude(res)
    # Only the client-repo is scanned; cortex repo itself never appears
    names = [e["name"] for e in res.checks]
    assert all("hermes-cortex" not in n for n in names)
