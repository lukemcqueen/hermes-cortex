#!/usr/bin/env python3
"""CR1 — cortex_gateway transport package.

Proves the extracted transport layer (TransportAdapter + TelegramAdapter +
bus helpers) in ops/scripts/cortex_gateway/ preserves msg-gateway.py's exact
behavior, importable as a package with no daemon/agent coupling.

Run: python3 -m pytest tests/test_cortex_gateway_transport.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

# Load the legacy msg-gateway module the same way test_msg_gateway.py does, so
# we can prove the extraction is a faithful parity (old vs new, same behavior).
_SPEC = importlib.util.spec_from_file_location(
    "msg_gateway", _REPO / "ops" / "scripts" / "msg-gateway.py")
GW = importlib.util.module_from_spec(_SPEC)
sys.modules["msg_gateway"] = GW
_SPEC.loader.exec_module(GW)

import gateway_envelope as env  # noqa: E402


# ── CR1.1 package is importable, exports the transport surface ──────────────
def test_transport_package_importable():
    from cortex_gateway import transport  # noqa: F401
    assert hasattr(transport, "TransportAdapter")
    assert hasattr(transport, "TelegramAdapter")
    assert hasattr(transport, "BotConfig")


def test_transport_bus_helpers_present():
    from cortex_gateway import transport
    for name in ("bus_send", "bus_read", "bus_archive", "_bus_headers"):
        assert callable(getattr(transport, name)), f"missing {name}"


# ── CR1.2 TransportAdapter is the same abstract interface ───────────────────
def test_transport_adapter_interface_unimplemented():
    from cortex_gateway.transport import TransportAdapter
    a = TransportAdapter()
    with pytest.raises(NotImplementedError):
        a.start()
    with pytest.raises(NotImplementedError):
        a.stop()
    with pytest.raises(NotImplementedError):
        a.parse({})
    with pytest.raises(NotImplementedError):
        a.send({})
    assert a.health() == {"ok": True}


# ── CR1.3 parse() parity with msg-gateway (extraction is faithful) ──────────
def _sample_update():
    return {
        "message": {
            "chat": {"id": 7},
            "text": "hello world",
            "date": 1,
            "message_thread_id": 3,
        }
    }


def test_telegram_parse_parity_with_msg_gateway():
    """msg-gateway parity for every field IT produced; the target may ADD fields.

    2026-10-02 (Luke: "build feature parity, and once we are confident, then cut over"):
    the parity TARGET for parse/send became the incumbent Hermes adapter — which carries
    media, captions, reply linkage, edits, reactions and callbacks that msg-gateway.py
    never had. Those arrive as ADDED fields (`tg_kind`, populated `media`/`reply_to_msg_id`),
    so the legacy parity assertion is now "every legacy field is still produced with the
    same value", not "the key sets are identical".
    """
    from cortex_gateway.transport import TelegramAdapter
    new = TelegramAdapter(token="t", initial_offset=0)
    raw = _sample_update()

    got = new.parse(raw)
    legacy = GW.TelegramAdapter(token="t", initial_offset=0).parse(raw)

    missing = set(legacy) - set(got)
    assert not missing, f"the extraction dropped legacy field(s): {sorted(missing)}"
    for k in legacy:
        if k == "msg_id":
            import uuid as _uuid
            _uuid.UUID(str(got[k]))  # must be a valid uuid, not shared
        else:
            assert got[k] == legacy[k], f"field {k} diverged from msg-gateway"
    assert got.get("tg_kind") == "message"        # the added discriminator

    # And the produced envelope validates against the contract.
    env.validate({**got, "to_agent": "x"})


def test_telegram_parse_none_cases_parity():
    from cortex_gateway.transport import TelegramAdapter
    new = TelegramAdapter(token="t")
    legacy = GW.TelegramAdapter(token="t")
    for raw in ({}, {"message": {}}, {"message": {"chat": {"id": 1}, "text": ""}},
                {"message": {"chat": {"id": 1}}}):
        assert new.parse(raw) is None
        assert legacy.parse(raw) is None


# ── CR1.4 send() uses chat_id, CHUNKS long bodies, and threads reply_to ─────
def test_telegram_send_contract(monkeypatch):
    """Chunking replaced truncation (2026-10-02, parity with the incumbent).

    The extracted transport used to send `body[:4000]` — silently dropping the tail of
    a long reply, which the parity audit named a material cutover risk. The incumbent
    chunks, so now the target does too: every call fits Telegram's limit, the pieces
    reconstruct the original exactly, and reply_to rides the FIRST chunk only.
    """
    from cortex_gateway.transport import TelegramAdapter
    a = TelegramAdapter(token="t")
    calls = []

    def fake_api(method, params):
        calls.append({"method": method, "params": dict(params)})
        return {"ok": True}

    monkeypatch.setattr(a, "_api", fake_api)
    body = "y" * 5000
    ok = a.send({"channel_user_id": 9, "body": body, "reply_to_msg_id": 5})
    assert ok is True
    assert all(c["method"] == "sendMessage" for c in calls)
    assert all(c["params"]["chat_id"] == 9 for c in calls)
    assert all(len(c["params"]["text"]) <= 4000 for c in calls)
    assert "".join(c["params"]["text"] for c in calls) == body, "no characters may be lost"
    assert len(calls) > 1, "a 5000-char body must be split"
    assert calls[0]["params"]["reply_to_message_id"] == 5
    assert all("reply_to_message_id" not in c["params"] for c in calls[1:])


def test_telegram_init_rejects_bad_token_and_offset():
    """A4 fuzz hardening: token/initial_offset are validated (None/empty/wrong
    type fails fast instead of building a broken bot at runtime)."""
    from cortex_gateway.transport import TelegramAdapter
    import pytest as _pt
    with _pt.raises((TypeError, ValueError)):
        TelegramAdapter(token=None)
    with _pt.raises((TypeError, ValueError)):
        TelegramAdapter(token="")
    with _pt.raises((TypeError, ValueError)):
        TelegramAdapter(token="t", initial_offset=None)
    with _pt.raises((TypeError, ValueError)):
        TelegramAdapter(token="t", initial_offset="x")
    # Valid values still construct.
    assert TelegramAdapter(token="t", initial_offset=3).offset == 3


def test_botconfig_from_dict_parity():
    from cortex_gateway.transport import BotConfig
    d = {"token_ref": "TOK", "channel": "telegram", "initial_offset": 3,
         "routing": {"default": "esther", "overrides": {"1": "codex"}}}
    new = BotConfig.from_dict(d)
    legacy = GW.BotConfig.from_dict(d)
    assert (new.token_ref, new.channel, new.initial_offset,
            new.routing_default, new.routing_overrides) == (
                legacy.token_ref, legacy.channel, legacy.initial_offset,
                legacy.routing_default, legacy.routing_overrides)
