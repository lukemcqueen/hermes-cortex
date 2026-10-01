#!/usr/bin/env python3
"""Regression test: the DOGFOOD gate must be scoped to the hermes-cortex repo.

Bug (Titus, reported 2026-10-01): Pi hit

    ❌  DOGFOOD — governance enforcer deployed copy differs from committed repo source.

when pushing from a REGULAR NON-CORTEX repo.

Why it happened: `core.hooksPath` is set GLOBALLY (~/.hermes-cortex/hooks), so
`pre-commit-score` runs in EVERY repo on the host. The DOGFOOD check compares
the hermes-cortex repo's HEAD enforcer against the DEPLOYED copy — a
cortex-internal sync state that no other repo can act on. It ran before the
`IS_CORTEX_REPO` guard (computed much later in the script), so one stale
deploy on one host hard-blocked every ordinary commit in every unrelated repo.
That is the "gates must be scoped to what they govern" rule.

The fix: the DOGFOOD block is guarded by the same `${HOME}/hermes-cortex`
comparison the IS_CORTEX_REPO guard uses.

Run: python3 -m pytest tests/test_dogfood_gate_scoping.py -q
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HOOK = (_REPO / "ops" / "scripts" / "pre-commit-score").read_text()

_GUARD_LINE = '_DOGFOOD_TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")'
_BLOCK_COND = 'if [[ "$_DOGFOOD_TOPLEVEL" == "${HOME}/hermes-cortex" && -n "$DOGFOOD_HEAD"'

# The guard expression, isolated so it can be executed for real.
_GUARD_EXPR = _GUARD_LINE + '\n[[ "$_DOGFOOD_TOPLEVEL" == "${HOME}/hermes-cortex" ]]'


# ── Structural: the guard exists and wraps the block ──────────

def test_dogfood_block_is_scoped_to_cortex_repo():
    """The DOGFOOD `if` must require the repo to be ${HOME}/hermes-cortex."""
    assert _BLOCK_COND in _HOOK, (
        "DOGFOOD block is not scoped to the hermes-cortex repo — a stale deploy "
        "would block commits in every unrelated repo (the Titus bug)")


def test_scope_guard_precedes_the_dogfood_branch():
    """The scope guard must be evaluated before the block body runs."""
    guard_i = _HOOK.index(_GUARD_LINE)
    block_i = _HOOK.index(_BLOCK_COND)
    assert guard_i < block_i, "scope guard must be computed before the DOGFOOD branch"


def test_unguarded_dogfood_condition_is_gone():
    """The old unscoped condition must not survive anywhere."""
    assert 'if [[ -n "$DOGFOOD_HEAD" && -f "$DOGFOOD_DEPLOY" ]]; then' not in _HOOK, (
        "the unscoped DOGFOOD condition is still present")


# ── Real behavior: run the actual guard expression ────────────

def _run_guard(cwd: Path) -> int:
    r = subprocess.run(["bash", "-c", _GUARD_EXPR], cwd=str(cwd),
                       capture_output=True, text=True)
    return r.returncode


def test_scope_guard_passes_in_the_cortex_repo():
    """In the real hermes-cortex repo the guard is satisfied (rc 0)."""
    if not (_REPO / ".git").exists():
        pytest.skip("not a git checkout")
    assert _run_guard(_REPO) == 0, "guard must be true in ~/hermes-cortex"


def test_scope_guard_rejects_a_foreign_repo():
    """A regular non-cortex repo must fail the guard — DOGFOOD never fires there."""
    with tempfile.TemporaryDirectory() as d:
        foreign = Path(d)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        assert _run_guard(foreign) != 0, (
            "guard must reject a non-cortex repo so its commits are never "
            "blocked by the cortex enforcer's deploy state")


def test_scope_guard_rejects_subdirectory_of_foreign_repo():
    """Being inside a nested dir of another repo still fails the guard."""
    with tempfile.TemporaryDirectory() as d:
        sub = Path(d) / "nested" / "deeper"
        sub.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        assert _run_guard(sub) != 0, "nested dir of a foreign repo must fail the guard"
