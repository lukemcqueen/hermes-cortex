"""api_send must enqueue the PARSED envelope, not the raw pre-serialized string.

Bug (2026-09-25, orch-skill-lifecycle discovery): the collector posts
``message`` as a JSON string (validate_send_payload tolerates both forms and
returns the parsed envelope as parsed_message), but api_send passed the RAW
string to bus.send(). PGMQ then stored a double-encoded JSON string body:
``body`` was `"{\\"from\\": \\"moses\\", ...}"` (jsonb_typeof = 'string').

Consequences: 123 inbox_orchestrator messages since Sep 15 archived as
unqueryable string bodies; handler subject-match filters silently missed them;
Learning Reports from direct collector sends were invisible to the shared
pipeline (only the forwarder's re-posted object copies worked).

Contract: bus.send() receives the parsed envelope dict. The stored body is a
jsonb OBJECT whose subject/from survive, and the mirror sees the same dict.
"""
import asyncio
import importlib.util
import json
import os
from unittest.mock import MagicMock, patch

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(TESTS_DIR, "..", "core", "cortex_bus", "server.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.normpath(path))
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = _load("cortex_bus_server_under_test", SERVER_PATH)


class _FakeRequest:
    """Minimal Request stand-in: async .json() + .client."""

    def __init__(self, payload):
        self._payload = payload
        self.client = None

    async def json(self):
        return self._payload


def _collector_payload(agent="moses"):
    """Exactly what agent-learning-collector.py posts (message pre-serialized)."""
    envelope = {
        "from": agent,
        "subject": "LEARNING_REPORT",
        "body": json.dumps({"topic": "reports", "text": f"━━━ Learning Report — {agent} ━━━"}),
        "priority": 80,
    }
    return {"queue": "inbox_orchestrator", "message": json.dumps(envelope)}


def _run_api_send(payload, bus, agent="moses"):
    with patch.object(server, "get_queue", return_value=bus), \
         patch.object(server, "_check_permission"), \
         patch.object(server, "_authenticate", return_value=agent), \
         patch.object(server, "_rate_limiter") as rl, \
         patch.object(server, "_log_audit"), \
         patch.object(server, "_mirror_to_orchestrator_inbox") as mirror:
        rl.allow.return_value = True
        resp = asyncio.run(server.api_send(_FakeRequest(payload)))
    return resp, mirror


def test_api_send_enqueues_parsed_object_for_string_message():
    bus = MagicMock()
    bus.send.return_value = "test-msg-id"
    resp, mirror = _run_api_send(_collector_payload("moses"), bus)
    assert resp == {"msg_id": "test-msg-id"}
    sent_body = bus.send.call_args[0][1]
    assert isinstance(sent_body, dict), (
        f"bus.send must receive the parsed envelope dict, got {type(sent_body).__name__}"
    )
    assert sent_body["subject"] == "LEARNING_REPORT"
    assert sent_body["from"] == "moses"
    # The mirror must see the same parsed envelope, not the raw string.
    mirrored = mirror.call_args[0][2]
    assert isinstance(mirrored, dict)
    assert mirrored["subject"] == "LEARNING_REPORT"


def test_api_send_enqueues_object_message_unchanged():
    bus = MagicMock()
    bus.send.return_value = "test-msg-id-2"
    envelope = {
        "from": "esther",
        "to": "orchestrator",
        "subject": "LEARNING_REPORT",
        "body": {"topic": "reports", "text": "body"},
        "priority": 80,
    }
    payload = {"queue": "inbox_orchestrator", "message": envelope}
    bus = MagicMock()
    bus.send.return_value = "test-msg-id-2"
    resp, mirror = _run_api_send(payload, bus, agent="esther")
    sent_body = bus.send.call_args[0][1]
    assert sent_body == envelope, "object messages must pass through unchanged"


def test_validator_parses_string_message():
    """The validator already parses string envelopes — api_send must USE that."""
    errors, parsed = server.validate_send_payload(
        _collector_payload(), authenticated_from="moses"
    )
    assert errors == []
    assert isinstance(parsed, dict)
    assert parsed["subject"] == "LEARNING_REPORT"
