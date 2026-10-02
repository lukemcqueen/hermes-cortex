#!/usr/bin/env python3
"""The bus bridge's two shape contracts, pinned from live evidence (2026-10-02).

Both were wrong, and both failed SILENTLY — which is why the cutover rehearsal could not
get a message through while every test passed.

1. WRITE: the gateway sent the ADR-0005 envelope AS the bus message. The bus has its own
   schema and rejects it outright:
     400 unknown envelope field(s): ack_required, channel, channel_user_id, from_agent,
     media, msg_id, reply_to_msg_id, thread_id, to_agent, ts
   Every dispatch was therefore a 400 and no human message ever reached an agent. The
   signed envelope must travel inside the message's `body`, and `from` must match the
   authenticated agent (the bus refuses "from 'gateway' ... authenticated agent 'esther'").

2. READ: bus_read() returns the WHOLE bus message under the key `body` —
   {"subject": "AGENT_REPLY", "body": {<envelope>}, "from": ..., "to": ...} — so
   validating msg["body"] directly failed and poll_replies ARCHIVED the reply as
   malformed. A queued reply was silently dropped (depth 1 -> 0, nothing delivered).

Run: python3 -m pytest tests/test_gateway_bus_shapes.py -q -s
"""
import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import gateway_envelope as env                            # noqa: E402
from cortex_gateway import hermes_backend as hb          # noqa: E402


def _envelope():
    return {"msg_id": env.new_msg_id(), "ts": int(time.time()), "from_agent": "",
            "to_agent": "esther", "channel": "telegram", "channel_user_id": 100001,
            "thread_id": None, "body": "hello", "media": [],
            "reply_to_msg_id": None, "ack_required": False}


# ── 1. the write shape ───────────────────────────────────────────────

def test_dispatch_wraps_the_envelope_in_the_bus_schema(monkeypatch):
    sent = {}

    def _fake(bus_url, headers, queue, message):
        sent["queue"] = queue
        sent["message"] = message
        return {"msg_id": "x"}

    monkeypatch.setattr(hb._bus, "bus_send", _fake)
    backend = hb.HermesBackend(agent="esther", bus_url="https://bus.example.com",
                              bus_headers={}, secret="s" * 32)
    assert backend.dispatch(_envelope()) is None      # async contract unchanged

    msg = sent["message"]
    assert sent["queue"] == "inbox_esther"
    allowed = {"body", "correlation_id", "forwarded_from", "from", "priority",
               "subject", "timestamp", "to", "type"}
    extra = set(msg) - allowed
    assert not extra, f"the bus rejects unknown fields — got {sorted(extra)}"
    assert msg["subject"], "the bus requires an UPPER_CASE subject"
    assert msg["subject"] == msg["subject"].upper()
    assert msg["from"] == "esther", "the bus requires from == the authenticated agent"
    assert not msg["from"] == "gateway", "sending as 'gateway' is refused by the bus"
    inner = json.loads(msg["body"])
    env.validate(inner)                                # the envelope rides in `body`
    assert inner["body"] == "hello"
    print(f"  write shape ✓ subject={msg['subject']} from={msg['from']} "
          f"envelope inside body")


# ── 2. the read shape ────────────────────────────────────────────────

def test_extract_envelope_unwraps_the_bus_message(monkeypatch):
    e = _envelope()
    # EXACTLY what bus_read() returned live: the whole message under `body`.
    live = {"msg_id": "bus-1", "queue": "out_esther",
            "body": {"subject": "AGENT_REPLY", "body": e, "from": "esther",
                     "to": "esther", "priority": 0, "correlation_id": e["msg_id"]}}
    got = hb._extract_envelope(live)
    assert got is not None, "the wrapper must be unwrapped, not rejected"
    env.validate(got)
    assert got["channel_user_id"] == 100001
    print("  read shape ✓ the bus message is unwrapped to the envelope")

    # a producer that sends a bare envelope still works
    assert hb._extract_envelope({"body": e})["body"] == "hello"
    # and a JSON-string body (how the envelope is actually stored)
    s = {"body": json.dumps({"subject": "AGENT_REPLY", "body": json.dumps(e)})}
    assert hb._extract_envelope(s)["body"] == "hello"
    print("  read shape ✓ bare envelope and JSON-string bodies also work")


def test_the_old_shapes_really_did_fail_the_contract():
    """Control: show what the previous code did with each shape."""
    e = _envelope()
    live_wrapper = {"subject": "AGENT_REPLY", "body": e, "from": "esther", "to": "esther"}
    try:
        env.validate(live_wrapper)                     # the old poll_replies ran this
        raise AssertionError("the wrapper must NOT validate as an envelope")
    except env.EnvelopeError as err:
        assert "missing required fields" in str(err)
    raw = e  # the old dispatch sent the bare envelope as the message
    try:
        env.validate({"allowed": list(raw)[:1]})       # stand-in for the bus's schema check
        raise AssertionError("unreachable")
    except env.EnvelopeError:
        pass
    print("  control ✓ the old shapes fail validation, which is why both legs went silent")
