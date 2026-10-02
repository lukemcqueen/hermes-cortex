#!/usr/bin/env python3
"""agent-reply: the generic agent-side reply primitive (routing from the origin).

Any agent that can run a command can answer the human. These tests pin the two things that
must never drift: the reply goes to `out_<agent>`, and its ROUTING comes from the origin
envelope — an agent supplies text, never a destination.

Run: python3 -m pytest tests/test_agent_reply_cli.py -q -s
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import gateway_envelope as env                                   # noqa: E402
import cortex_gateway.transport as T                             # noqa: E402

_spec = importlib.util.spec_from_file_location("agent_reply_cli", _REPO / "ops" / "scripts" / "agent-reply.py")
assert _spec and _spec.loader
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


class _Bus:
    def __init__(self):
        self.sent = []

    def send(self, bus_url, headers, queue, message):
        self.sent.append((queue, message))
        return {"msg_id": "bus-1"}


def _origin():
    return {"msg_id": env.new_msg_id(), "ts": int(time.time()), "from_agent": "",
            "to_agent": "pi", "channel": "telegram", "channel_user_id": 4242,
            "thread_id": 7, "body": "what is 2+2?", "media": [],
            "reply_to_msg_id": None, "ack_required": False}


def _run(monkeypatch, argv):
    bus = _Bus()
    monkeypatch.setattr(T, "bus_send", bus.send)
    monkeypatch.setattr(cli, "_bus_config", lambda: ("https://bus.example.com", {}))
    rc = cli.main(argv)
    return rc, bus


def test_reply_routes_from_the_origin_to_out_agent(monkeypatch, capsys):
    origin = _origin()
    rc, bus = _run(monkeypatch, ["--agent", "pi", "--origin-json", json.dumps(origin),
                                 "--text", "4"])
    assert rc == 0
    assert bus.sent, "nothing was published"
    queue, msg = bus.sent[0]
    assert queue == "out_pi", f"the reply must go to out_<agent>, got {queue}"
    assert msg["subject"] == "AGENT_REPLY"
    assert msg["from"] == "pi", "the bus requires from == the authenticated agent"
    reply = json.loads(msg["body"])
    env.validate(reply)
    # routing copied from the origin — channel, chat, thread
    assert reply["channel"] == "telegram" and reply["channel_user_id"] == 4242
    assert reply["thread_id"] == 7
    assert reply["body"] == "4"
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["queued_for"] == "out_pi" and out["chat"] == 4242
    print(f"  reply routes from the origin → out_pi (receipt {out['msg_id'][:8]}…) ✓")


def test_proactive_message_states_routing_explicitly(monkeypatch):
    rc, bus = _run(monkeypatch, ["--agent", "esther", "--channel", "telegram",
                                 "--chat", "99", "--text", "heads up"])
    assert rc == 0
    reply = json.loads(bus.sent[0][1]["body"])
    assert reply["channel_user_id"] == 99 and reply["channel"] == "telegram"
    print("  proactive send (no origin) uses explicit routing ✓")


def test_refuses_empty_text_no_origin_and_no_agent(monkeypatch):
    for argv, expect in (
        (["--agent", "pi", "--origin-json", "{}", "--text", "   "], "empty reply"),
        (["--agent", "pi", "--text", "hi"], "need an origin"),
        (["--origin-json", "{}", "--text", "hi"], "no agent name"),
    ):
        try:
            _run(monkeypatch, argv)
            raise AssertionError(f"{argv} must refuse")
        except SystemExit as e:
            assert expect in str(e), f"expected {expect!r}, got {e}"
    print("  empty text, missing origin and missing agent all refuse ✓")


def test_failed_publish_is_loud_and_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(T, "bus_send", lambda *a, **k: None)     # the bus refuses
    monkeypatch.setattr(cli, "_bus_config", lambda: ("https://bus.example.com", {}))
    rc = cli.main(["--agent", "pi", "--origin-json", json.dumps(_origin()), "--text", "4"])
    err = capsys.readouterr().err
    assert rc == 1, "a failed publish must exit non-zero"
    assert "NOT delivered" in err and "out_pi" in err
    print("  a refused publish exits 1 and says the reply was NOT delivered ✓")
