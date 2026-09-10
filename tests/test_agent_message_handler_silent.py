"""agent-message-handler silent-subject classification.

Regression test for the HEALTH_* pickup-notify loop (2026-09-10):
the handler's own report_health_change() sends HEALTH_PERSISTENT_ISSUES
to inbox_health_check with to=moses; the bus US-002 mirror copies it into
inbox_orchestrator; the handler polls that queue, picks up its own
mirrored report, and fires the 📥 pickup notify to Telegram every 5 min.

Fix: HEALTH_* subjects are self-generated telemetry — classify them as
silent noise (archive, no notify) alongside DOCTOR_TEST/STATUS_REQUEST.
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
    # The script imports hermes_paths from the deployed scripts dir at top level
    sys_path_backup = list(sys.path)
    sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts"))
    spec.loader.exec_module(amh)
    sys.path[:] = sys_path_backup
    return amh


def test_health_persistent_issues_is_silent(handler_module):
    assert handler_module._is_silent_subject("HEALTH_PERSISTENT_ISSUES") is True


def test_health_issue_variants_are_silent(handler_module):
    assert handler_module._is_silent_subject("HEALTH_ISSUES_DETECTED") is True
    assert handler_module._is_silent_subject("HEALTH_HEALTHY_NOW") is True
    # The error RESULT echo that used to compound the loop is also HEALTH_*
    assert handler_module._is_silent_subject("HEALTH_PERSISTENT_ISSUES_RESULT") is True


def test_protocol_probes_still_silent(handler_module):
    for s in ("DOCTOR_TEST", "STATUS_REQUEST", "HEARTBEAT", "PING"):
        assert handler_module._is_silent_subject(s) is True


def test_real_subjects_still_visible(handler_module):
    for s in ("EXEC", "UPDATE_REQUEST", "TASK_REQUEST", "PROPOSAL"):
        assert handler_module._is_silent_subject(s) is False


def test_result_subjects_dispatched_but_not_notified(handler_module):
    # *_RESULT replies must still reach dispatch (they close task rows),
    # so they are NOT silent-archived — but the pickup notify is noise.
    for s in ("TASK_RESULT", "EXEC_RESULT", "UPDATE_RESULT", "EXEC_RESULT", "STATUS_RESULT"):
        assert handler_module._is_silent_subject(s) is False
        assert handler_module._notify_on_pickup(s) is False


def test_non_result_subjects_still_notify(handler_module):
    # A genuine inbound non-task message (e.g. a health check request on
    # a remote queue, or a tracked-but-not-result message) still notifies.
    assert handler_module._notify_on_pickup("PING_REQUEST") is True


def test_none_input_does_not_crash(handler_module):
    assert handler_module._is_silent_subject(None) is False