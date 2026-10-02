#!/usr/bin/env python3
"""CR3 — cortex_gateway daemon + hermes backend.

The daemon wires the two seams into the full poll → dispatch → reply loop:
Telegram poll → envelope → route → BackendAdapter.dispatch → reply →
Telegram send, with poll_bot + drain_outbound and the dispatch/reply step
between poll and drain. hermes is the reference backend (bus inbox/out_<agent>).

Run: python3 -m pytest tests/test_cortex_gateway_daemon.py -q
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

# Import the package at MODULE level so it is cached in sys.modules. The
# function-level `from cortex_gateway.daemon import Gateway` calls then resolve
# from the cache and are immune to other test modules/conftest resetting
# sys.path between tests (the full-suite isolation failure this fixes).
import cortex_gateway.daemon  # noqa: E402,F401
import cortex_gateway.backend  # noqa: E402,F401
import cortex_gateway.hermes_backend  # noqa: E402,F401
import cortex_gateway.transport  # noqa: E402,F401

BUS = "http://example.com"


# ── fakes ───────────────────────────────────────────────────────────────────
class FakeBus:
    """In-memory bus standing in for PGMQ (records sends, serves reads)."""

    def __init__(self):
        self.sent = []            # (queue, message)
        self.outbox = []          # replies the agent produced
        self.archived = []

    def send(self, url, headers, queue, message):
        self.sent.append((queue, message))
        return True

    def read(self, url, headers, queue, vt=60):
        if queue == "out_hermes" and self.outbox:
            # Real bus returns a bus msg_id PLUS the envelope as `body`.
            return {"msg_id": f"bus-{len(self.outbox)}",
                    "body": self.outbox.pop(0)}
        return {"msg_id": None}

    def archive(self, url, headers, queue, msg_id):
        self.archived.append((queue, msg_id))
        return True


def _update(text, chat_id=7):
    return {"update_id": 100, "message": {"chat": {"id": chat_id}, "text": text,
                                          "date": 1}}


class FakeTransport:
    """Records get_updates/send; stands in for TelegramAdapter."""

    def __init__(self, updates):
        self._updates = updates
        self.sent = []
        self.offset = 0

    def start(self):
        pass

    def stop(self):
        pass

    def get_updates(self, timeout=30):
        return self._updates

    def send(self, envelope):
        self.sent.append(envelope)
        return True

    def parse(self, raw):
        msg = raw.get("message")
        if not msg or not msg.get("text"):
            return None
        return {"msg_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "ts": 1,
                "from_agent": "", "to_agent": "", "channel": "telegram",
                "channel_user_id": msg["chat"]["id"], "thread_id": None,
                "body": msg["text"], "media": [], "reply_to_msg_id": None,
                "ack_required": False}


def _update_env(text):
    return {"msg_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "ts": 1,
            "from_agent": "user", "to_agent": "hermes", "channel": "telegram",
            "channel_user_id": 7, "thread_id": None, "body": text, "media": [],
            "reply_to_msg_id": None, "ack_required": False}


# ── CR3.1 BackendAdapter gains a default poll_replies (async backends) ──────
def test_backend_adapter_default_poll_replies_empty():
    from cortex_gateway.backend import BackendAdapter

    class B(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            return None

        def health(self):
            return {"ok": True}

    assert B().poll_replies() == []


# ── CR3.2 HermesBackend: dispatch → inbox_<agent>, poll_replies → out_<agent> ─
def test_hermes_backend_dispatch_enqueues_to_inbox(monkeypatch):
    """The bus message WRAPS the signed envelope — and this test used to encode the bug.

    It previously asserted `msg["body"] == "hi"`, i.e. the envelope's text sent as the bus
    message's body. That shape passes against a fake bus and is a 400 against the real one
    ("unknown envelope field(s): ack_required, channel, ..."), so every dispatch was
    rejected while this test stayed green. The contract is now the bus's schema, with the
    signed envelope as the message body payload (docs/design/gateway-reply-path.md).
    """
    import json as _json

    from cortex_gateway import hermes_backend as hb
    from cortex_gateway import transport

    bus = FakeBus()
    monkeypatch.setattr(transport, "bus_send", bus.send)
    monkeypatch.setattr(transport, "bus_read", bus.read)

    b = hb.HermesBackend(agent="hermes", bus_url=BUS, bus_headers={},
                         secret="s")
    b.start()
    env = _update_env("hi")
    reply = b.dispatch(env)
    assert reply is None, "hermes is async — dispatch returns no immediate reply"
    assert bus.sent and bus.sent[0][0] == "inbox_hermes"

    msg = bus.sent[0][1]
    # 1. the bus's own schema: only these keys, `from` == the authenticated agent
    allowed = {"body", "correlation_id", "forwarded_from", "from", "priority",
               "subject", "timestamp", "to", "type"}
    assert not (set(msg) - allowed), f"the bus rejects unknown fields: {sorted(set(msg) - allowed)}"
    assert msg["from"] == "hermes"
    assert msg["subject"] == msg["subject"].upper()
    # 2. the signed envelope rides INSIDE the message body
    inner = _json.loads(msg["body"])
    assert inner["body"] == "hi"
    assert inner.get("gateway_sig"), "hermes backend must sign inbound"
    print("  dispatch wraps the signed envelope in the bus schema ✓")


def test_hermes_backend_dispatch_none_and_malformed_are_silent(monkeypatch):
    """A4 fuzz hardening: dispatch(None)/non-dict returns None, never raises."""
    from cortex_gateway import hermes_backend as hb

    b = hb.HermesBackend(agent="hermes", bus_url=BUS, bus_headers={},
                         secret="s")
    assert b.dispatch(None) is None
    assert b.dispatch("not-a-dict") is None
    assert b.dispatch({}) is None  # missing required fields → DLQ


def test_hermes_backend_poll_replies_drains_outbox(monkeypatch):
    from cortex_gateway import hermes_backend as hb
    from cortex_gateway import transport

    bus = FakeBus()
    reply_env = _update_env("agent says hi")
    bus.outbox.append(reply_env)
    monkeypatch.setattr(transport, "bus_send", bus.send)
    monkeypatch.setattr(transport, "bus_read", bus.read)
    monkeypatch.setattr(transport, "bus_archive", bus.archive)

    b = hb.HermesBackend(agent="hermes", bus_url=BUS, bus_headers={},
                         secret="s")
    out = b.poll_replies()
    assert len(out) == 1
    assert out[0]["body"] == "agent says hi"
    assert bus.archived, "consumed reply must be archived (archive-after-send)"


# ── CR3.3 daemon full turn: Telegram → dispatch → reply → send ──────────────
def test_daemon_poll_dispatch_send(monkeypatch):
    from cortex_gateway.daemon import Gateway
    from cortex_gateway.backend import BackendAdapter

    transport = FakeTransport([_update("ping")])

    class Sync(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            self.last = envelope
            return {**envelope, "body": "pong",
                    "from_agent": envelope["to_agent"],
                    "to_agent": envelope["from_agent"]}

        def health(self):
            return {"ok": True}

    backend = Sync()
    gw = Gateway(transport=transport, backends={"hermes": backend},
                 default_agent="hermes")
    gw.poll_once()
    assert backend.last["body"] == "ping"
    assert transport.sent, "sync reply must be delivered via transport"
    assert transport.sent[0]["body"] == "pong"
    assert transport.offset == 101, "offset advances after a successful turn"


def test_daemon_drains_async_replies(monkeypatch):
    from cortex_gateway.daemon import Gateway
    from cortex_gateway.backend import BackendAdapter

    transport = FakeTransport([_update("ping")])
    async_reply = _update_env("async pong")

    class Async(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            return None  # async: reply comes later via poll_replies

        def poll_replies(self, max_n=5):
            return [async_reply]

        def health(self):
            return {"ok": True}

    gw = Gateway(transport=transport, backends={"hermes": Async()},
                 default_agent="hermes")
    gw.poll_once()
    gw.drain_outbound()
    assert any(e["body"] == "async pong" for e in transport.sent), \
        "async reply must be drained and sent"


def test_daemon_silent_backend_sends_nothing():
    from cortex_gateway.daemon import Gateway
    from cortex_gateway.backend import BackendAdapter

    transport = FakeTransport([_update("ping")])

    class Silent(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            return None

        def health(self):
            return {"ok": True}

    gw = Gateway(transport=transport, backends={"hermes": Silent()},
                 default_agent="hermes")
    gw.poll_once()
    gw.drain_outbound()
    assert transport.sent == []
    assert transport.offset == 101, "offset still advances on silent turn"


def test_daemon_routes_by_channel_user():
    from cortex_gateway.daemon import Gateway
    from cortex_gateway.backend import BackendAdapter

    transport = FakeTransport([_update("hi", chat_id=42)])

    class Spy(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            self.got = envelope
            return None

        def health(self):
            return {"ok": True}

    spy_hermes = Spy()
    spy_pi = Spy()
    gw = Gateway(transport=transport,
                 backends={"hermes": spy_hermes, "pi": spy_pi},
                 default_agent="hermes",
                 routing_overrides={"42": "pi"})
    gw.poll_once()
    assert spy_pi.got["to_agent"] == "pi", "channel_user 42 must route to pi"
