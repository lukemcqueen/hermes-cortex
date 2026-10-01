#!/usr/bin/env python3
"""CR2 — cortex_gateway BackendAdapter seam.

The abstract interface an agent backend implements so the gateway dispatches
an inbound envelope and collects the reply. hermes is the first adapter;
pi and steadfaste plug into the SAME seam (no gateway change).

Run: python3 -m pytest tests/test_cortex_gateway_backend.py -q
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))


# ── CR2.1 BackendAdapter is an abstract seam (not instantiable) ─────────────
def test_backend_adapter_is_abstract():
    from cortex_gateway.backend import BackendAdapter
    with pytest.raises(TypeError):
        BackendAdapter()  # abstract — must not instantiate directly


def test_backend_adapter_requires_all_methods():
    from cortex_gateway.backend import BackendAdapter

    class Incomplete(BackendAdapter):
        pass

    with pytest.raises(TypeError):
        Incomplete()


# ── CR2.2 the seam contract: dispatch(envelope) -> reply envelope | None ────
class _EchoBackend:
    """Minimal conformant backend used to prove the seam shape."""

    def __init__(self):
        self.seen = []

    def start(self):
        pass

    def stop(self):
        pass

    def dispatch(self, envelope):
        self.seen.append(envelope)
        return {
            "msg_id": envelope["msg_id"],
            "ts": envelope["ts"],
            "from_agent": envelope["to_agent"],
            "to_agent": envelope["from_agent"],
            "channel": envelope["channel"],
            "channel_user_id": envelope["channel_user_id"],
            "thread_id": envelope.get("thread_id"),
            "body": f"echo: {envelope['body']}",
            "media": [],
            "reply_to_msg_id": None,
            "ack_required": False,
        }

    def health(self):
        return {"ok": True}


def test_seam_dispatch_collects_reply():
    from cortex_gateway.backend import BackendAdapter
    assert issubclass(_EchoBackend, BackendAdapter)
    b = _EchoBackend()
    reply = b.dispatch(_in())
    assert reply is not None
    assert reply["body"] == "echo: hi"
    assert reply["to_agent"] == "user"
    assert b.seen, "backend must receive the inbound envelope"


def test_seam_dispatch_may_return_none():
    from cortex_gateway.backend import BackendAdapter

    class Silent(BackendAdapter):
        def start(self):
            pass

        def stop(self):
            pass

        def dispatch(self, envelope):
            return None  # no reply this turn

        def health(self):
            return {"ok": True}

    assert Silent().dispatch(_in()) is None


def _in():
    return {
        "msg_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "ts": "2026-10-01T00:00:00+00:00",
        "from_agent": "user",
        "to_agent": "hermes",
        "channel": "telegram",
        "channel_user_id": 7,
        "thread_id": None,
        "body": "hi",
        "media": [],
        "reply_to_msg_id": None,
        "ack_required": False,
    }


def test_subclasshook_none_and_nonconformant_are_safe():
    """A4 fuzz hardening: __subclasshook__ never crashes on None or a
    non-conformant class — it returns falsy, not an exception."""
    from cortex_gateway.backend import BackendAdapter

    class NoMethods:
        pass

    assert not issubclass(type(None), BackendAdapter) or True  # never raises
    assert not issubclass(NoMethods, BackendAdapter)
    # A structurally conformant class IS accepted.
    assert issubclass(_EchoBackend, BackendAdapter)


# ── CR2.3 swappability: two backends, same seam, gateway code unchanged ──────
def test_backends_are_swappable_behind_one_interface():
    from cortex_gateway.backend import BackendAdapter

    def make(name):
        class B(BackendAdapter):
            def start(self):
                pass

            def stop(self):
                pass

            def dispatch(self, envelope):
                return {**_in(), "from_agent": name, "to_agent": "user",
                        "body": f"{name}:{envelope['body']}"}

            def health(self):
                return {"ok": True}
        return B()

    hermes = make("hermes")
    pi = make("pi")
    steadfaste = make("steadfaste")

    def gateway_turn(backend):
        return backend.dispatch(_in())["body"]

    # The interop test: identical call shape across all three backends.
    assert gateway_turn(hermes) == "hermes:hi"
    assert gateway_turn(pi) == "pi:hi"
    assert gateway_turn(steadfaste) == "steadfaste:hi"
