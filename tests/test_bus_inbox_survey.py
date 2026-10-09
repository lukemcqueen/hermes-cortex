"""Hermetic tests for ops/scripts/bus/bus-inbox-survey.sh.

The survey runs in fixture mode (BUS_SURVEY_FIXTURE=<file>) so the
pending / urgent / blocked / DLQ / truncation logic is exercised
without a live bus.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "scripts" / "bus" / "bus-inbox-survey.sh"


def run_survey(tmp_path, fixture):
    fx = tmp_path / "fixture.json"
    fx.write_text(json.dumps(fixture))
    env = dict(os.environ)
    env["BUS_SURVEY_FIXTURE"] = str(fx)
    env["BUS_SURVEY_PEEK_LIMIT"] = "500"
    env.pop("CORTEX_BUS_TOKEN", None)
    return subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=30)


def test_clean_is_reported_clean(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 0, "processing": 0, "dlq": False},
        {"name": "inbox_esther_dlq", "depth": 0, "processing": 0, "dlq": True},
    ], "messages": {}})
    assert r.returncode == 0, r.stderr
    assert "RESULT: clean" in r.stdout


def test_pending_normal_priority_is_not_actionable(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 1, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": 0, "subject": "PING"}]}})
    assert r.returncode == 0, r.stderr
    assert "pending: inbox_esther" in r.stdout
    assert "RESULT: clean" in r.stdout
    assert "urgent=0" in r.stdout


@pytest.mark.parametrize("priority,marker", [(20, "CRITICAL:"), (10, "URGENT:")])
def test_high_int_priority_is_actionable(tmp_path, priority, marker):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 1, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": priority, "subject": "EXEC"}]}})
    assert r.returncode == 0, r.stderr
    assert marker in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_string_urgent_priority_is_actionable(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 1, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": "critical", "subject": "EXEC"}]}})
    assert r.returncode == 0, r.stderr
    assert "CRITICAL:" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_numeric_string_priority_is_actionable(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 1, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": "20", "subject": "EXEC"}]}})
    assert r.returncode == 0, r.stderr
    assert "CRITICAL:" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_unknown_priority_is_flagged_not_downgraded(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 1, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": "high", "subject": "EXEC"}]}})
    assert r.returncode == 0, r.stderr
    assert "WARN:" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_truncated_queue_is_actionable(tmp_path):
    # depth 3 but only 1 message visible -> a hidden critical cannot be missed
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther", "depth": 3, "processing": 0, "dlq": False},
    ], "messages": {"inbox_esther": [{"priority": 0, "subject": "PING"}]}})
    assert r.returncode == 0, r.stderr
    assert "TRUNCATED:" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_dlq_backlog_is_actionable(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "inbox_esther_dlq", "depth": 3, "processing": 0, "dlq": True},
    ], "messages": {}})
    assert r.returncode == 0, r.stderr
    assert "DLQ:" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_blocked_workflow_is_actionable(tmp_path):
    r = run_survey(tmp_path, {"queues": [
        {"name": "workflow_step_result", "depth": 2, "processing": 0, "dlq": False},
    ], "messages": {}})
    assert r.returncode == 0, r.stderr
    assert "BLOCKED: workflow_step_result" in r.stdout
    assert "RESULT: actionable" in r.stdout


def test_bad_response_shape_fails_closed(tmp_path):
    r = run_survey(tmp_path, {"queues": "not-a-list"})
    assert r.returncode == 1
    assert "FAIL:" in r.stderr
