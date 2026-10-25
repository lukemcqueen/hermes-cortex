"""The bus MCP must be able to (a) set correlation_id on a send and (b) read a
queue back WITHOUT consuming it — the two halves of the dispatch-verification
loop (task row 5c200dd0, "orch-bus-worker on esther cannot VERIFY a bus
dispatch — its dispatch half is structurally fire-and-forget").

Before this change: `_inbox_send` never put `correlation_id` in the envelope even
though the bus ingestion allowlist accepts it (AGENTS.md §Bus Message Contract),
so a delivered EXEC_RESULT was unmatchable by the 6-checkpoint rule; and the only
read tool `_inbox_read` was a CONSUMING `POST /api/pgmq/read` on the caller's own
queue, so it could never see the orchestrator queue where results land.

These tests exercise the changed functions themselves (not a neighbour).

Run: python3 -m pytest tests/test_bus_mcp_verify_surface.py -q
"""

import importlib.util
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "cortex_bus_mcp_verify", _REPO / "mcp-servers" / "cortex-bus-mcp.py"
)
_bus = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_bus)


def _capture_request(monkeypatch, response_body, status=200):
    """Record every (method, path, body) _request is called with; return the log."""
    calls = []

    def fake_request(method, path, body=None, cascade_on=None):
        calls.append({"method": method, "path": path, "body": body})
        return status, response_body

    monkeypatch.setattr(_bus, "_request", fake_request)
    return calls


def test_inbox_send_carries_correlation_id_in_envelope(monkeypatch):
    """AC-1: the correlation id reaches the POSTED envelope, not just a return value."""
    calls = _capture_request(monkeypatch, "{}")

    _bus._inbox_send({"to": "joseph", "subject": "EXEC", "body": "probe",
                      "correlation_id": "corr-abc123"})

    assert len(calls) == 1, "one recipient = one send"
    sent = calls[0]
    assert sent["path"] == "api/pgmq/send"
    envelope = json.loads(sent["body"]["message"])
    assert envelope["correlation_id"] == "corr-abc123", (
        "the bus allowlist accepts correlation_id; the MCP must actually set it "
        "or the 6-checkpoint result match is impossible"
    )
    # The rest of the envelope is untouched.
    assert envelope["subject"] == "EXEC"
    assert envelope["to"] == "joseph"
    assert envelope["from"]
    assert json.loads(envelope["body"])["text"] == "probe"


def test_inbox_send_omits_correlation_id_when_absent(monkeypatch):
    """Legacy callers see a byte-identical envelope: no key when none is given."""
    calls = _capture_request(monkeypatch, "{}")

    _bus._inbox_send({"to": "joseph", "subject": "EXEC", "body": "probe"})

    envelope = json.loads(calls[0]["body"]["message"])
    assert "correlation_id" not in envelope, (
        "an unspecified correlation_id must not appear as an empty key — that "
        "would change the envelope for every existing caller"
    )


def test_inbox_send_blank_correlation_id_is_treated_as_absent(monkeypatch):
    """A whitespace-only id is 'absent', not an empty envelope field."""
    calls = _capture_request(monkeypatch, "{}")

    _bus._inbox_send({"to": "joseph", "subject": "EXEC", "body": "probe",
                      "correlation_id": "   "})

    assert "correlation_id" not in json.loads(calls[0]["body"]["message"])


def test_inbox_send_task_passes_correlation_id_through(monkeypatch):
    """A delegated task carries its id so its TASK result can be matched."""
    captured = {}

    def fake_send(args):
        captured.update(args)
        return type("R", (), {"content": [type("T", (), {"text": "Message sent."})()]})()

    monkeypatch.setattr(_bus, "_inbox_send", fake_send)

    _bus._inbox_send_task({"agent": "titus", "description": "run the probe",
                           "correlation_id": "task-corr-9"})

    assert captured.get("correlation_id") == "task-corr-9"


def test_bus_inbox_peek_never_consumes(monkeypatch):
    """AC-2: the verification read is GET-only and never POST /api/pgmq/read.

    A read that consumed the result it is trying to observe would destroy the
    evidence and could starve the queue's real consumer.
    """
    calls = _capture_request(monkeypatch, json.dumps({"queue": "inbox_orchestrator",
                                                      "messages": [], "count": 0}))

    _bus._bus_inbox_peek({"queue": "inbox_orchestrator", "limit": 5})

    assert calls, "peek must actually issue a request"
    for c in calls:
        assert c["method"] == "GET", f"peek must not use {c['method']}"
        assert "api/pgmq/read" not in c["path"], "peek must never dequeue"
    assert calls[0]["path"] == "api/pgmq/peek/inbox_orchestrator?limit=5"


def test_bus_inbox_peek_archived_uses_archives_endpoint(monkeypatch):
    """Archived results are found via /archives; pending via /peek."""
    calls = _capture_request(monkeypatch, json.dumps({"messages": []}))

    _bus._bus_inbox_peek({"queue": "inbox_orchestrator", "limit": 3, "archived": True})

    assert calls[0]["path"] == "api/pgmq/archives/inbox_orchestrator?limit=3"
    assert calls[0]["method"] == "GET"


def test_bus_inbox_peek_exposes_correlation_id_from_nested_body(monkeypatch):
    """The bus nests the envelope as a JSON string inside the message body."""
    inner = {"from": "esther", "to": "orchestrator", "subject": "DOCTOR_TEST",
             "correlation_id": "doctor-e2e-6e14d85e", "priority": 0}
    fixture = json.dumps({"queue": "inbox_orchestrator", "count": 1, "messages": [
        {"msg_id": "msg-1", "enqueued_at": "2026-10-25 13:20:25.593081+00",
         "read_ct": 0, "body": json.dumps(inner)},
    ]})
    _capture_request(monkeypatch, fixture)

    result = _bus._bus_inbox_peek({"queue": "inbox_orchestrator"})
    payload = json.loads(result.content[0].text)

    assert payload["count"] == 1
    entry = payload["messages"][0]
    assert entry["correlation_id"] == "doctor-e2e-6e14d85e", (
        "the whole point: the caller must see the id it can match a result on"
    )
    assert entry["subject"] == "DOCTOR_TEST"
    assert entry["from"] == "esther"
    assert entry["msg_id"] == "msg-1"


def test_bus_inbox_peek_reports_http_failure_not_an_empty_queue(monkeypatch):
    """A 401 must never read as 'nothing arrived' (error-swallow guard)."""
    _capture_request(monkeypatch, "Unauthorized", status=401)

    result = _bus._bus_inbox_peek({"queue": "inbox_moses"})
    text = result.content[0].text

    assert "peek failed" in text
    assert "401" in text


def test_bus_inbox_peek_defaults_to_orchestrator_queue(monkeypatch):
    """The default queue is the one dispatch results actually land in."""
    calls = _capture_request(monkeypatch, json.dumps({"messages": []}))

    _bus._bus_inbox_peek({})

    assert calls[0]["path"].startswith("api/pgmq/peek/inbox_orchestrator")
