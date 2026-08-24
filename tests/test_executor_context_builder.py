#!/usr/bin/env python3
"""Tests for the executor context-builder (12-Factor F3/F13 pre-fetch).

Dexter Horthy factor-13: "If you already know what tools you'll want the
model to call, call them DETERMINISTICALLY and let the model do the hard
part of figuring out how to use their outputs." For a coding agent
dispatched to a worktree, the likely-needed context is knowable in advance:
repo rules (AGENTS.md/CLAUDE.md), the slice plan, recent git history, and
the diff being built on. Pre-fetching these into the execution_request
envelope saves the agent tool round-trips and keeps it focused on the task.

Run: python3 -m pytest tests/test_executor_context_builder.py -q
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "executor_context", _REPO / "ops" / "scripts" / "executor_context_builder.py")
ecb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ecb)


@pytest.fixture
def git_repo(tmp_path):
    """A real git repo with AGENTS.md, CLAUDE.md, and a commit."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t.t"],
                   check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"],
                   check=True)
    (tmp_path / "AGENTS.md").write_text("# Rules\n- R1: no bypass\n")
    (tmp_path / "CLAUDE.md").write_text("# Governance\n- same rules\n")
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "app.py").write_text("def main():\n    pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"],
                   check=True)
    return tmp_path


# ── F13: pre-fetch tests ─────────────────────────────────────

def test_builds_rules_context(git_repo):
    ctx = ecb.build_context(str(git_repo), task="add tests", plan="slice-1")
    assert "AGENTS.md" in ctx or "R1: no bypass" in ctx
    assert "CLAUDE.md" in ctx or "same rules" in ctx


def test_builds_plan_and_task(git_repo):
    ctx = ecb.build_context(str(git_repo), task="add tests", plan="slice-1")
    assert "add tests" in ctx
    assert "slice-1" in ctx


def test_includes_recent_git_history(git_repo):
    ctx = ecb.build_context(str(git_repo), task="t", plan="p")
    assert "init" in ctx  # the recent commit message


def test_no_repo_returns_error(git_repo):
    empty = git_repo.parent / "not-a-repo"
    empty.mkdir()
    ctx = ecb.build_context(str(empty), task="t", plan="p")
    assert "error" in ctx


def test_context_is_budgeted(git_repo):
    """The envelope must respect a token budget (F3: own the window)."""
    ctx = ecb.build_context(str(git_repo), task="t", plan="p", max_chars=500)
    assert len(ctx) <= 500 + 50  # small tolerance for framing


def test_missing_plan_is_ok(git_repo):
    ctx = ecb.build_context(str(git_repo), task="t")
    assert "TASK" in ctx
