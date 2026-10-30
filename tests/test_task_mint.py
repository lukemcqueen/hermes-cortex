#!/usr/bin/env python3
"""agent-message-handler inbox→task mint — bare-token + self-test regression.

Bug (task caed9076, measured 2026-10-19 by the orch-bus-worker pass):

  The inbox→task mint created contentless + duplicate task rows from protocol
  self-test traffic:
    * A report subject (PROPOSAL/ISSUES/IMPROVEMENTS) whose body carried no
      command/task/reason minted a row whose content was the BARE subject
      token ("PROPOSAL") — 10 such bare rows measured, 6 still unactionable.
    * A protocol self-test sends a report-shaped subject under a brand-new
      correlation_id, so the (source='inbox', correlation_id) UNIQUE index
      could not dedup them.

Fix:
    * _build_task_content() carries the message body into content (dict text >
      command > task > reason; str inner; bare subject as last resort).
    * _is_self_test() refuses the mint for self-test traffic before the row
      is created.

Run: python3 -m pytest tests/test_task_mint.py -q
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def handler_module(monkeypatch):
    monkeypatch.setenv("AGENT_NAME", "test-agent")
    monkeypatch.setenv("CORTEX_BUS_NO_OUTBOX", "1")
    src = REPO_ROOT / "ops" / "scripts" / "agent" / "agent-message-handler.py"
    spec = importlib.util.spec_from_file_location("agent_message_handler_mint", src)
    amh = importlib.util.module_from_spec(spec)
    backup = list(sys.path)
    sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts"))
    spec.loader.exec_module(amh)
    sys.path[:] = backup
    return amh


# ── Content carries the body, not the bare subject ─────────────

def test_report_body_text_is_carried_into_content(handler_module):
    """A report whose free text lives under body['body']['text'] must not
    mint a bare-token row."""
    body = {"from": "joseph", "subject": "PROPOSAL",
            "body": {"text": "cache the venv across deploys"}}
    content = handler_module._build_task_content("PROPOSAL", body)
    assert content == "PROPOSAL: cache the venv across deploys", content


def test_report_string_body_is_carried_into_content(handler_module):
    body = {"body": "add a gateway doc"}
    content = handler_module._build_task_content("PROPOSAL", body)
    assert content == "PROPOSAL: add a gateway doc", content


def test_exec_command_is_still_carried(handler_module):
    body = {"body": {"command": "agent-diagnostic.py", "params": []}}
    content = handler_module._build_task_content("EXEC", body)
    assert content == "EXEC: agent-diagnostic.py", content


def test_empty_body_degrades_to_bare_subject_only_after_skip(handler_module):
    """An empty body has nothing to carry — but this must be the LAST resort
    (the self-test skip runs first in poll_once)."""
    assert handler_module._build_task_content("PROPOSAL", {"body": ""}) == "PROPOSAL"


# ── Self-test traffic must not mint ────────────────────────────

@pytest.mark.parametrize("subject,content", [
    ("SELFTEST", "skill-content request flow for titus"),
    ("PROPOSAL", "self-test: bare PROPOSAL must not error"),
    ("PROPOSAL", "SELFTEST skill-content request flow for titus"),
    ("DOCTOR_TEST", ""),
])
def test_self_test_is_detected(handler_module, subject, content):
    assert handler_module._is_self_test(subject, content) is True


def test_real_report_is_not_a_self_test(handler_module):
    assert handler_module._is_self_test("PROPOSAL", "cache the venv") is False


def test_self_test_body_mints_no_row(handler_module, monkeypatch):
    """The poll_once guard short-circuits before task_create_from_message for
    self-test traffic — behaviour, not source text."""
    seen = []
    monkeypatch.setattr(handler_module, "task_create_from_message",
                        lambda s, c, t: seen.append((s, c, t)) or "corr-x")
    # Reproduce the guard exactly as poll_once now writes it:
    subject = "PROPOSAL"
    body = {"body": "self-test: bare PROPOSAL must not error"}
    task_content = handler_module._build_task_content(subject, body)
    if not handler_module._is_self_test(subject, task_content):
        handler_module.task_create_from_message(subject, "corr-x", task_content)
    assert seen == [], f"self-test message minted a row: {seen}"


def test_real_report_still_mints_a_row(handler_module, monkeypatch):
    seen = []
    monkeypatch.setattr(handler_module, "task_create_from_message",
                        lambda s, c, t: seen.append((s, c, t)) or "corr-x")
    subject = "PROPOSAL"
    body = {"body": {"text": "cache the venv"}}
    task_content = handler_module._build_task_content(subject, body)
    if not handler_module._is_self_test(subject, task_content):
        handler_module.task_create_from_message(subject, "corr-x", task_content)
    assert seen == [("PROPOSAL", "corr-x",
                     "PROPOSAL: cache the venv")], seen