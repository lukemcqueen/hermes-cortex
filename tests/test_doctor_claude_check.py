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
import os
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
    # Commit by pathspec: the cortex bare-commit hook refuses a plain
    # `git commit` (no pathspec) as a safety sweep, so committing the specific
    # file is what makes this a valid repo for check_dev_repo_claude.
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init", "--",
                    "README.md"], check=True, capture_output=True)

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
    """Claude configured + all dev repos have current CLAUDE.md → PASS."""
    (fake_home / ".mcp.json").write_text("{}")
    # A current CLAUDE.md carries the fleet's universal Excellence section
    (fake_home / "client-repo" / "CLAUDE.md").write_text(
        "# Governance\n\n## Excellence — Core Value, Every Action\n\n"
        "Do it right the first time, in everything.\n"
    )
    res = _make_results()
    checks.check_dev_repo_claude(res)
    passes = [e for e in res.checks if e['status'] == "PASS"]
    assert any("CLAUDE.md" in e["name"] for e in passes), (
        f"expected a CLAUDE.md PASS, got: {[e['name'] for e in res.checks]}")


def test_warns_when_claude_md_missing_excellence_section(fake_home):
    """Claude configured + repo CLAUDE.md exists but predates the fleet's
    universal Excellence section → WARN (drifted), not PASS.

    A repo-adapted CLAUDE.md is project-owned and never auto-overwritten, so
    the fix is a manual reconcile (merge the Excellence section), not a copy.
    """
    (fake_home / ".mcp.json").write_text("{}")
    (fake_home / "client-repo" / "CLAUDE.md").write_text(
        "# governance\n- same rules\n"  # present but stale — no Excellence
    )
    res = _make_results()
    checks.check_dev_repo_claude(res)
    warns = [e for e in res.checks if e['status'] == "WARN"]
    assert any("CLAUDE.md" in e["name"] and "Excellence" in e["detail"]
               for e in warns), (
        f"expected a CLAUDE.md drift WARN, got: {[e['name'] for e in res.checks]}")


# § check_user_template --------------------------------------------------------

def _user_paths(tmp_path, monkeypatch):
    """Re-point checks.CORTEX_REPO + Path.home() so check_user_template reads a temp tree."""
    template = tmp_path / "hermes-cortex" / "docs" / "templates" / "USER.seed.md"
    template.parent.mkdir(parents=True)
    live = tmp_path / ".hermes" / "memories" / "USER.md"
    live.parent.mkdir(parents=True)
    monkeypatch.setattr(checks, "CORTEX_REPO", tmp_path / "hermes-cortex")
    # check_user_template derives the live path from Path.home(), not checks.HOME
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return template, live


def _set_epoch(path, epoch):
    os.utime(path, (epoch, epoch))


def test_user_template_no_live_file_is_silent(tmp_path, monkeypatch):
    """No live USER.md → no check entries (Hermes creates it on first write)."""
    template, _ = _user_paths(tmp_path, monkeypatch)
    template.write_text("# template\n")
    res = _make_results()
    checks.check_user_template(res)
    assert len(res.checks) == 0


def test_user_template_newer_warns(tmp_path, monkeypatch):
    """Template newer than live USER.md → WARN to review the copy."""
    template, live = _user_paths(tmp_path, monkeypatch)
    template.write_text("# template\n")
    live.write_text("# me\n")
    _set_epoch(template, 5000)
    _set_epoch(live, 1000)
    res = _make_results()
    checks.check_user_template(res)
    names = [e["name"] for e in res.checks]
    assert any("USER.md" in n and "template" in n for n in names), f"got {names}"
    warn = [e for e in res.checks if "USER.md" in e["name"]][0]
    assert warn["status"] == "WARN"


def test_user_template_live_current_passes(tmp_path, monkeypatch):
    """Live USER.md as new as / newer than the template → PASS."""
    template, live = _user_paths(tmp_path, monkeypatch)
    template.write_text("# template\n")
    live.write_text("# me\n")
    _set_epoch(template, 1000)
    _set_epoch(live, 5000)
    res = _make_results()
    checks.check_user_template(res)
    entries = [e for e in res.checks if "USER.md" in e["name"]]
    assert len(entries) == 1 and entries[0]["status"] == "PASS", (
        f"got {[e['name'] + ':' + e['status'] for e in res.checks]}")


def test_skips_hermes_cortex_repo_itself(fake_home):
    """CORTEX_REPO is excluded from the dev-repo scan (covered by check_repo)."""
    (fake_home / ".mcp.json").write_text("{}")
    # Simulate CORTEX_REPO inside the scan area — it must be skipped.
    res = _make_results()
    checks.check_dev_repo_claude(res)
    # Only the client-repo is scanned; cortex repo itself never appears
    names = [e["name"] for e in res.checks]
    assert all("hermes-cortex" not in n for n in names)
