#!/usr/bin/env python3
"""Tests for cortex-dogfood.sh default-branch resolution.

Regression test (Luke 2026-08-24, hour-long incident): dogfood hardcoded
`git pull --rebase origin main`, which after the PII history rewrite pulled
the stale pre-rewrite main and re-triggered a stuck interactive rebase
(unmerged files) that broke the deploy sync and push gate.

The fix: dogfood must resolve the remote's ACTUAL default branch
(symbolic-ref refs/remotes/origin/HEAD), falling back to main only when
the remote HEAD symref is absent.

Run: python3 -m pytest tests/test_dogfood_default_branch.py -q
"""
import re
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_DOGFOOD = (_REPO / "ops" / "scripts" / "cortex-dogfood.sh").read_text()


def _extract_default_branch_logic() -> str:
    """Pull the default-branch resolution block out of cortex-dogfood.sh."""
    m = re.search(r"_DEFAULT_BRANCH=\$\(.*?\n  \(cd \"\$REPO\" && git pull --rebase origin \"\$_DEFAULT_BRANCH\"",
                  _DOGFOOD, re.S)
    assert m, "default-branch resolution block not found in cortex-dogfood.sh"
    return m.group(0)


# ── RED tests: the resolution logic must exist and use origin/HEAD ──

def test_dogfood_does_not_hardcode_main_pull():
    """The pull line must reference a variable, not a literal 'main'."""
    assert "git pull --rebase origin main" not in _DOGFOOD, (
        "dogfood still hardcodes 'origin main' — will pull stale history after rewrite")


def test_dogfood_resolves_remote_default_branch():
    """The pull must resolve origin/HEAD (the remote's actual default)."""
    block = _extract_default_branch_logic()
    assert "symbolic-ref refs/remotes/origin/HEAD" in block, (
        "must resolve the remote default branch via symbolic-ref origin/HEAD")
    assert 'origin "$_DEFAULT_BRANCH"' in block, (
        "pull must target the resolved default branch variable")


def test_dogfood_falls_back_to_main_when_no_remote_head():
    """If origin/HEAD symref is absent, fall back to 'main' (never empty)."""
    block = _extract_default_branch_logic()
    assert '|| echo "main"' in block or "|| echo main" in block, (
        "must fall back to main when the origin/HEAD symref is missing")


# ── Real-behavior test: the actual command resolves on this host ──

def test_resolution_command_works_on_live_repo():
    """Run the exact resolution command against the live repo."""
    r = subprocess.run(
        ["git", "-C", str(_REPO), "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True)
    if r.returncode == 0:
        branch = r.stdout.strip().replace("refs/remotes/origin/", "")
        assert branch, "resolved default branch must be non-empty"
    else:
        pytest.skip("remote origin/HEAD symref not configured on this host — "
                    "fallback path expected")
