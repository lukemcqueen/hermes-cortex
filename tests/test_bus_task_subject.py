"""inbox_send_task must send a bus-LEGAL subject (UPPER_CASE protocol name).

Regression (2026-09-23): `_inbox_send_task` built
`subject = f"Task: {description[:80]}"`. The Agent Bus rejects that at ingestion
("subject: required UPPER_CASE protocol name (A-Z0-9_)"), so EVERY orchestrator
task delegation through the cortex-bus MCP tool failed with
"Send failed across all endpoints" — observed live while delegating a
verification task to titus. The receiver-side handler tolerates a `Task:`
prefix, but that path is unreachable when the bus refuses the message first.

Run: python3 -m pytest tests/test_bus_task_subject.py -q
"""

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "cortex_bus_mcp_subject", _REPO / "mcp-servers" / "cortex-bus-mcp.py"
)
_bus = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_bus)

# The bus's ingestion rule: UPPER_CASE protocol name, A-Z0-9_ only.
_BUS_SUBJECT_RE = re.compile(r"^[A-Z0-9_]+$")


def _fake_result(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_inbox_send_task_sends_bus_legal_subject(monkeypatch):
    """The subject must satisfy the bus validator, not just the local handler."""
    captured = {}
    monkeypatch.setattr(
        _bus, "_inbox_send", lambda args: (captured.update(args), _fake_result("Message sent to titus"))[1]
    )

    _bus._inbox_send_task({"agent": "titus", "description": "run the gate probe"})

    subject = captured.get("subject", "")
    assert subject, "inbox_send_task must pass a subject to _inbox_send"
    assert _BUS_SUBJECT_RE.match(subject), (
        f"bus rejects this subject at ingestion: {subject!r} "
        "(required UPPER_CASE protocol name, A-Z0-9_)"
    )
    assert subject == "TASK_REQUEST", "canonical task-creating subject (handler TASK_CREATING_SUBJECTS)"


def test_inbox_send_task_keeps_description_in_body(monkeypatch):
    """The human-readable description rides in the body, not the subject."""
    captured = {}
    monkeypatch.setattr(
        _bus, "_inbox_send", lambda args: (captured.update(args), _fake_result("Message sent to titus"))[1]
    )

    _bus._inbox_send_task({"agent": "titus", "description": "run the gate probe", "priority": "urgent"})

    body = json.loads(captured["body"])
    assert body["type"] == "task_delegation"
    assert body["description"] == "run the gate probe"
    assert body["priority"] == "urgent"
    assert body["requester"], "the delegation must name its requester"


def test_inbox_send_task_reports_failed_when_send_fails(monkeypatch):
    """A refused send must never be reported as created."""
    monkeypatch.setattr(
        _bus,
        "_inbox_send",
        lambda args: _fake_result('Send failed across all endpoints. Last error: {"detail":"Invalid message"}'),
    )

    result = _bus._inbox_send_task({"agent": "titus", "description": "run the gate probe"})

    payload = json.loads(result.content[0].text)
    assert payload["status"] == "failed", "a bus refusal must surface as failed, not created"
