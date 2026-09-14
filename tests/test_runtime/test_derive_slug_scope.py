"""Regression: loop-gov-mcp _derive_slug must not trust the MCP process cwd.

Gotcha (2026-09-14): governance locks for a cron session were mis-scoped —
the MCP derived repo_slug from ITS OWN cwd (the hermes-agent git checkout)
rather than the session repo (hermes-cortex), so the git hooks
(pre-commit-score / pre-push-pull, which derive the slug from the repo they
run in) could not match the lock and blocked every commit/push on
hermes-cortex.

Root cause: _derive_slug() ran `git rev-parse --show-toplevel` from the MCP
daemon's cwd FIRST. When that cwd is inside ANY git checkout (the Hermes
install is one), it returned that repo's basename and never reached the
canonical `~/hermes-cortex` fallback.

The fix: prefer the canonical governed repo (`$HOME/hermes-cortex`) before
consulting the MCP process cwd — the daemon's cwd is a launch artifact and is
never a reliable signal of the session's working repo. Same for the enforcer
plugin's _derive_repo_slug(). Portable across Linux and macOS (Path.home only).
"""
import importlib.util
import types
from pathlib import Path

import pytest

_HOME = str(Path.home())

# ── Load loop-gov-mcp.py (hyphen in path → spec_from_file_location) ──
_MCP_PATH = Path(__file__).resolve().parents[2] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp", _MCP_PATH)
_loop_gov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_loop_gov)

# ── Load the enforcer plugin (mirror test_governance_bypass.py) ──
_ENFORCER_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "governance-enforcer" / "__init__.py"
)
_espec = importlib.util.spec_from_file_location("governance_enforcer", _ENFORCER_PATH)
_enforcer = importlib.util.module_from_spec(_espec)
_espec.loader.exec_module(_enforcer)


def _fake_git_foreign_check_output_factory(mcp_module: types.ModuleType):
    """Return an object mocking subprocess.check_output so the MCP process cwd
    appears to be inside a FOREIGN git repo (the bug scenario: the Hermes
    install checkout, basename 'hermes-agent')."""

    def fake_check_output(*args, **kwargs):
        raise FileNotFoundError  # git not reachable the way the test drives it

    return fake_check_output


class TestDeriveSlugPrefersCanonicalGovernedRepo:
    """The MCP cwd is a launch artifact (can be the hermes-agent git checkout).

    When the canonical governed repo `$HOME/hermes-cortex` exists, _derive_slug
    must return `hermes-cortex` regardless of what git repo the MCP daemon
    process cwd happens to resolve to. Otherwise the git hooks (which derive
    the slug from the actual committed repo) cannot match the lock and block
    commit/push.
    """

    @pytest.fixture
    def fake_home(self, tmp_path):
        """A HOME containing a governed `hermes-cortex` repo (with .git)."""
        gov = tmp_path / "hermes-cortex"
        (gov / ".git").mkdir(parents=True)
        return tmp_path

    def test_prefers_canonical_repo_over_foreign_cwd(self, fake_home, monkeypatch):
        """When the governed repo exists, the slug is hermes-cortex even if the
        MCP cwd would resolve to a foreign git repo (hermes-agent)."""
        monkeypatch.setattr(_loop_gov, "HOME", fake_home)
        # Simulate the MCP cwd being inside a foreign git checkout: git is
        # reachable but would resolve to 'hermes-agent' — we make the cwd
        # git resolution a no-op so the canonical check is the ONLY source.
        monkeypatch.setattr(
            _loop_gov.subprocess,
            "check_output",
            lambda *a, **k: (fake_home / "does-not-exist").name.encode(),
        )
        assert _loop_gov._derive_slug() == "hermes-cortex"

    def test_falls_back_to_cwd_git_when_no_canonical_repo(self, tmp_path, monkeypatch):
        """No governed repo exists (project-repo-only machine): derive from the
        session cwd's git repo basename."""
        proj = tmp_path / "client-alpha"
        (proj / ".git").mkdir(parents=True)
        # Canonical repos absent:
        assert not (tmp_path / "hermes-cortex").exists()
        monkeypatch.setattr(_loop_gov, "HOME", tmp_path)
        monkeypatch.setattr(
            _loop_gov.subprocess,
            "check_output",
            lambda *a, **k: str(proj).encode(),
        )
        assert _loop_gov._derive_slug() == "client-alpha"

    def test_enforcer_derive_repo_slug_prefers_canonical(self, fake_home, monkeypatch):
        """The enforcer plugin's _derive_repo_slug must match: prefer the
        canonical governed repo over the gateway process cwd."""
        monkeypatch.setattr(_enforcer.subprocess, "run", None) if hasattr(
            _enforcer, "subprocess"
        ) else None
        # Point Path.home at the fake HOME, then exercise the canonical-repo
        # branch: patch subprocess so git-from-cwd returns the foreign repo,
        # and assert the canonical repo still wins.
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr(
            _enforcer.subprocess,
            "run",
            lambda *a, **k: types.SimpleNamespace(
                returncode=0, stdout=(str(fake_home / "hermes-agent") + "\n")
            ),
        )
        assert _enforcer._derive_repo_slug() == "hermes-cortex"