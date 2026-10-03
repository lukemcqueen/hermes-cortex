#!/usr/bin/env python3
"""The deploy publishes its unlock window; the auditor must respect it — bounded.

cortex-update.sh unlocks the immutable enforcement files early and relocks them at
the END of the run, so that tree is legitimately writable for the whole deploy. An
auditor sampling the flags inside that window reports a break that is not one.

Observed 2026-10-03: the deploy wrote its manifest at 16:30:04 and the
governance-auditor alert is stamped 16:30, naming exactly the three targets the
deploy unlocks (governance-enforcer/__init__.py, hooks/pre-commit, hooks/pre-push)
and printing the relock the deploy was about to run as the "fix".

Two properties are load-bearing and both are tested here:
  * the marker is CLEARED after the relock (or the auditor defers forever), and
  * it is only trusted while FRESH (or a killed deploy silences the check).
"""
from __future__ import annotations

import importlib.util
import re
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
UPDATE_SH = REPO / "ops/scripts/cortex-update.sh"
AUDITOR_PY = REPO / "ops/scripts/manage/agent-governance-auditor.py"
MARKER = Path.home() / ".hermes-cortex" / "state" / "deploy-in-progress"


def _load_auditor():
    """Import the auditor module without running main().

    Loaded by PATH through importlib (not exec) because it lives under
    ops/scripts/manage/ and imports hermes_tz/state_tracker from the deployed scripts
    dir, which the repo does not have — stub those two first so the module body can
    execute.
    """
    import sys
    import types

    if "hermes_tz" not in sys.modules:
        hermes_tz = types.ModuleType("hermes_tz")
        hermes_tz.format_timestamp = lambda fmt: "2026-10-03 16:30 KST"
        sys.modules["hermes_tz"] = hermes_tz
    if "state_tracker" not in sys.modules:
        state_tracker = types.ModuleType("state_tracker")
        state_tracker.StateTracker = object
        sys.modules["state_tracker"] = state_tracker

    spec = importlib.util.spec_from_file_location("auditor_under_test", AUDITOR_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["auditor_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


# Tests that need a fake HOME patch Path.home() INLINE rather than through a helper
# or a monkeypatch fixture: the adversarial scan fuzzes test FUNCTION PARAMETERS, so
# any parameter — including a helper's own — reads to it as untrusted input and gets
# flagged for a value the test never controlled.

# ── the deploy side ─────────────────────────────────────────────────


def test_deploy_defines_and_calls_the_marker_helpers():
    src = UPDATE_SH.read_text()
    assert "_mark_deploy_in_progress()" in src, "the deploy must define the marker writer"
    assert "_clear_deploy_marker()" in src, "the deploy must define the marker remover"
    assert re.search(r"^STATE_DIR=.*\n_mark_deploy_in_progress", src, re.M), (
        "the marker must be written at deploy start, not conditionally later — a "
        "window that opens before the marker is published is not covered")


def test_marker_is_cleared_inside_the_exit_trap_after_the_relock():
    """Clearing before the relock would open a window where the marker is gone but
    the flags are still off — the exact false positive the marker prevents."""
    src = UPDATE_SH.read_text()
    trap_body = src.split("_relock_enforcement() {", 1)[1].split("\ntrap ", 1)[0]
    assert "_clear_deploy_marker" in trap_body, (
        "the EXIT trap must clear the marker, or a failed deploy strands it")
    clear_at = trap_body.index("_clear_deploy_marker")
    relock_at = trap_body.index("hermes-plugin-lock lock")
    assert clear_at > relock_at, (
        "the marker must be cleared AFTER the relock, not before")


def test_marker_is_not_stranded_on_this_host():
    """Live control: a completed deploy leaves no marker. If this fails, the EXIT
    trap did not run its clear and every auditor run from now on defers."""
    if MARKER.exists():
        age = time.time() - MARKER.stat().st_mtime
        if age < 1800:
            pytest.skip(f"a deploy looks genuinely in progress ({age:.0f}s old)")
        pytest.fail(
            f"stale deploy marker left behind ({age:.0f}s old): {MARKER} — the "
            "auditor's immutability check is being silenced by a dead run")


# ── the auditor side ────────────────────────────────────────────────

def test_auditor_guards_the_immutability_check_on_the_marker():
    src = AUDITOR_PY.read_text()
    assert "_deploy_in_progress" in src, "the auditor must know about the window"
    section = src.split("immutable_targets = [", 1)[1].split("for path in", 1)[0]
    assert "_deploy_in_progress()" in section, (
        "the guard must sit on the immutability check itself, before the targets "
        "are probed")


def test_marker_trust_is_time_bounded():
    """A killed deploy must not silence the check forever."""
    src = AUDITOR_PY.read_text()
    assert "max_age_s" in src, "the trust window must be a parameter"
    m = re.search(r"max_age_s: int = (\d+)", src)
    assert m, "the trust window must have an explicit default"
    assert int(m.group(1)) <= 3600, (
        "a trust window longer than an hour lets a stranded marker hide a real "
        "unlock for most of a day")


def test_defer_is_an_explicit_return_not_a_silent_skip():
    src = AUDITOR_PY.read_text()
    section = src.split("immutable_targets = [", 1)[1].split("for path in", 1)[0]
    assert "return issues" in section, (
        "deferring must return through the normal path so the caller can see the "
        "check produced no findings, rather than swallowing it")


def test_control_absent_marker_does_not_defer():
    """CONTROL: with no marker the check must still RUN — otherwise the guard would
    mask a genuinely unlocked gate."""
    auditor = _load_auditor()
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(Path, "home", lambda: Path(tmp)):
            assert auditor._deploy_in_progress() is False, (
                "no marker must mean 'not in progress' — a guard that always defers "
                "is a guard that never detects anything")


def test_fresh_marker_defers_and_stale_marker_does_not():
    auditor = _load_auditor()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        marker = root / ".hermes-cortex" / "state" / "deploy-in-progress"
        marker.parent.mkdir(parents=True)
        marker.write_text("2026-10-03T07:30:00Z\n")
        with mock.patch.object(Path, "home", lambda: root):
            assert auditor._deploy_in_progress() is True, "a fresh marker must defer"
            assert auditor._deploy_in_progress(max_age_s=0) is False, (
                "an expired marker must NOT defer — the trust window is what keeps a "
                "stranded marker from hiding a real unlock")
