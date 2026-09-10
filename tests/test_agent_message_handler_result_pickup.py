"""TASK_RESULT pickup-notify noise (Luke 2026-09-10 flood report).

Regression: agent-message-handler.py's pickup notify fires for every subject
NOT in TASK_CREATING_SUBJECTS (R-14 exempted EXEC/TASK_REQUEST because
task-db.py's entry notify replaces it) — but result subjects (*_RESULT) fall
into that gap: each TASK_RESULT/EXEC_RESULT reply arriving at the orchestrator
produced a "📥 [esther] Received TASK_RESULT from moses" Telegram message,
one per result, flooding the chat. Results are receipts, not pickups: they are
logged (📬) and transition the task to completed silently.

Contract: _should_skip_pickup_notify(subject) is True for result subjects,
False for real command subjects that still need a pickup notice.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def handler_module(monkeypatch):
    """Load agent-message-handler.py by file path (hyphenated name)."""
    monkeypatch.setenv("AGENT_NAME", "test-agent")
    monkeypatch.setenv("CORTEX_BUS_NO_OUTBOX", "1")
    src = REPO_ROOT / "ops" / "scripts" / "agent" / "agent-message-handler.py"
    spec = importlib.util.spec_from_file_location("agent_message_handler", src)
    amh = importlib.util.module_from_spec(spec)
    sys_path_backup = list(sys.path)
    sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts"))
    spec.loader.exec_module(amh)
    sys.path[:] = sys_path_backup
    return amh


def test_task_result_does_not_notify_pickup(handler_module):
    assert handler_module._should_skip_pickup_notify("TASK_RESULT") is True


def test_all_result_subjects_silent(handler_module):
    for s in ("EXEC_RESULT", "UPDATE_RESULT", "DIAGNOSTIC_RESULT",
              "ROLLBACK_RESULT", "FIX_RESULT", "LEARNINGS_RESULT",
              "STATUS_RESULT", "GIT_AUTH_RESULT", "TASK_RESULT"):
        assert handler_module._should_skip_pickup_notify(s) is True, s


def test_result_error_echo_variants_silent(handler_module):
    # send_bus_result fallback form "<subject>_RESULT" on unknown/error paths
    assert handler_module._should_skip_pickup_notify("SKILL_REPORT_RESULT") is True
    assert handler_module._should_skip_pickup_notify("UNKNOWN_THING_RESULT") is True


def test_command_subjects_still_get_pickup_notify(handler_module):
    # Non-tracked, non-result subjects keep the pickup notice
    assert handler_module._should_skip_pickup_notify("GIT_AUTH_CHECK") is False
    assert handler_module._should_skip_pickup_notify("FIX_REQUEST") is False


def test_tracked_subjects_still_skipped_via_r14(handler_module):
    # R-14: TASK_CREATING_SUBJECTS entry notify comes from task-db.py
    for s in ("EXEC", "UPDATE_REQUEST", "TASK_REQUEST", "PROPOSAL", "ISSUES",
              "IMPROVEMENTS"):
        assert handler_module._should_skip_pickup_notify(s) is True, s


def test_none_input_does_not_crash(handler_module):
    assert handler_module._should_skip_pickup_notify(None) is False