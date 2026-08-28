#!/usr/bin/env python3
"""Regression tests for joseph PROPOSAL 2026-08-28 (send-a599fb202e60).

The doctor's check_script_naming flagged lib/bus_outbox.py on every host
("Script naming"/"Script prefix" WARNs) even though running a lib/ module
directly as a no_agent cron is a documented pattern (install-crons.sh
agent-bus-retry-sweep). And the handler never created a task row for
"PROPOSAL: <what>" subjects because TASK_CREATING_SUBJECTS is an
exact-match check.

Fix:
1. check_script_naming exempts script targets under lib/ (shared library
   modules are not cron scripts).
2. agent-message-handler normalizes PROPOSAL:/ISSUES:/IMPROVEMENTS:
   prefixes to their tracked subjects.

Run: python3 -m pytest tests/test_script_naming_lib_exempt.py -q
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402


class _FakeResults:
    """Minimal stand-in for cortex_doctor.results.Results (add only)."""

    def __init__(self):
        self.items = []

    def add(self, name, severity, detail, fix):
        self.items.append((name, severity, detail, fix))


@pytest.fixture
def naming_results(tmp_path, monkeypatch):
    jobs_file = tmp_path / "jobs.json"
    monkeypatch.setattr(checks, "JOBS_FILE", jobs_file)
    return jobs_file, _FakeResults()


def _write_jobs(jobs_file, jobs):
    jobs_file.write_text(json.dumps({"jobs": jobs}))


def _run_naming_check(jobs_file, res):
    _write_jobs(jobs_file, [{
        "name": "agent-bus-retry-sweep",
        "script": "lib/bus_outbox.py",
        "no_agent": True,
    }])
    checks.check_script_naming(res)
    return res.items


def test_lib_script_target_is_exempt(naming_results):
    """lib/bus_outbox.py (documented direct-module cron) must NOT warn."""
    jobs_file, res = naming_results
    items = _run_naming_check(jobs_file, res)
    assert items == [], f"lib/ script target flagged: {items}"


def test_non_lib_mismatched_script_still_warns(naming_results):
    """The exemption must be narrow — real mismatches still warn."""
    jobs_file, res = naming_results
    _write_jobs(jobs_file, [{
        "name": "agent-bus-retry-sweep",
        "script": "manage/unrelated-script.py",
        "no_agent": True,
    }])
    checks.check_script_naming(res)
    names = {i[0] for i in res.items}
    assert "Script naming: agent-bus-retry-sweep" in names
    assert "Script prefix: agent-bus-retry-sweep" in names


def _load_handler():
    # hermes_paths lives in ops/scripts/ — the handler's ensure_scripts_path
    # import resolves it at module level.
    if str(_REPO / "ops" / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO / "ops" / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "agent_message_handler",
        _REPO / "ops" / "scripts" / "agent" / "agent-message-handler.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Import without executing the module body's runtime deps — the module
    # only imports hermes_paths at module level; commands is lazy.
    sys.modules["agent_message_handler"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("subject,expected", [
    ("PROPOSAL: doctor flags lib pattern", "PROPOSAL"),
    ("ISSUES: bus down", "ISSUES"),
    ("IMPROVEMENTS: add wrapper", "IMPROVEMENTS"),
    ("PROPOSAL", "PROPOSAL"),          # exact form passes through
    ("EXEC run doctor", "EXEC run doctor"),  # unrelated subject untouched
])
def test_normalize_tracked_subject(subject, expected):
    mod = _load_handler()
    assert mod.normalize_tracked_subject(subject) == expected
    assert mod.normalize_tracked_subject(subject) in \
        mod.TASK_CREATING_SUBJECTS or ":" not in subject
