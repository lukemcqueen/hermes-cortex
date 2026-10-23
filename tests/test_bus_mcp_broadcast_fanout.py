"""inbox_send with recipient "all" must fan out one message per agent to
inbox_<agent> — never to the unconsumed `broadcast` queue.

Defect (2026-10-22, escalated by esther 2026-10-23): cortex-bus-mcp.py
mapped recipient "all" → queue "broadcast", but nothing consumes that queue
(agent-message-handler.py and cortex-bus-processor.py read only inbox_<agent>).
Every send-to-"all" (FLEET_NOTICE, post-commit notify) was silently dropped:
the Excellence FLEET_NOTICE (918e292e) sat pending 29h delivered to nobody.

Documented fix (docs/fleet-update-protocol.md line 58): one message per agent
to inbox_<agent>. This test pins the fan-out behavior and forbids the
"broadcast" queue as a target.

Run: python3 -m pytest tests/test_bus_mcp_broadcast_fanout.py -q
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "cortex_bus_mcp_fanout", _REPO / "mcp-servers" / "cortex-bus-mcp.py"
)
_bus = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_bus)

_FLEET = ["moses", "esther", "joseph", "gisu", "kustos", "titus"]


def _text(result) -> str:
    return result.content[0].text


def test_inbox_send_all_fans_out_one_per_agent(monkeypatch):
    """recipient "all" sends one message per fleet agent to inbox_<agent>."""
    sends = []
    monkeypatch.setattr(_bus, "_request", lambda method, path, body=None, cascade_on=None: (
        sends.append((method, path, body)), (200, json.dumps({"msg_id": "t"}))
    )[1])

    result = _bus._inbox_send({
        "to": "all", "subject": "FLEET_NOTICE", "body": "pull + update",
        "topic": "fleet-notice", "priority": "normal",
    })

    assert len(sends) == len(_FLEET), f"expected {len(_FLEET)} sends, got {len(sends)}"
    for method, path, body in sends:
        assert (method, path) == ("POST", "api/pgmq/send")
        assert body["queue"] in {f"inbox_{a}" for a in _FLEET}, body["queue"]
        assert "broadcast" not in body["queue"], (
            "the unconsumed broadcast queue must never be a fan-out target"
        )
    queues = {body["queue"] for _, _, body in sends}
    assert queues == {f"inbox_{a}" for a in _FLEET}, "every fleet agent's inbox must be targeted exactly once"
    assert "all" in _text(result).lower()


def test_inbox_send_all_reports_partial_failures(monkeypatch):
    """A failed fan-out leg must be reported, not silently swallowed."""
    attempts = []
    monkeypatch.setattr(_bus, "_request", lambda method, path, body=None, cascade_on=None: (
        attempts.append(path),
        (503, "Bus unavailable") if len(attempts) == 1 else (200, json.dumps({"msg_id": "t"}))
    )[1])

    result = _bus._inbox_send({
        "to": "all", "subject": "FLEET_NOTICE", "body": "pull + update",
        "topic": "fleet-notice", "priority": "normal",
    })

    assert len(attempts) == len(_FLEET)
    assert "failed" in _text(result).lower() or "error" in _text(result).lower() or "not" in _text(result).lower()


def test_inbox_send_single_recipient_still_direct(monkeypatch):
    """A named recipient still goes to exactly one inbox — no regression."""
    sends = []
    monkeypatch.setattr(_bus, "_request", lambda method, path, body=None, cascade_on=None: (
        sends.append(body), (200, json.dumps({"msg_id": "t"}))
    )[1])

    _bus._inbox_send({
        "to": "titus", "subject": "EXEC", "body": "run script",
        "topic": "fleet-test", "priority": "normal",
    })

    assert len(sends) == 1
    assert sends[0]["queue"] == "inbox_titus"
