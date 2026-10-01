#!/usr/bin/env python3
"""CR4b — the gateway must fail closed on an empty GATEWAY_SECRET.

An empty HMAC key still produces a `gateway_sig`, but anyone can forge it —
so an unset secret silently degrades the gateway's "agents MUST verify"
guarantee to theatre. These tests pin the fail-closed behaviour at every
layer: signing, verifying, backend construction, and daemon start-up.
"""
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

# Module-level import → cached in sys.modules (immune to sys.path resets).
import gateway_envelope as ENV  # noqa: E402
import cortex_gateway.daemon as DAEMON  # noqa: E402
import cortex_gateway.hermes_backend as HB  # noqa: E402

EXAMPLE = _REPO / "ops" / "scripts" / "gateway.yaml.example"
CHAT = "12345"


def _env():
    return ENV.make_envelope(to_agent="esther", channel="telegram",
                             channel_user_id=CHAT, body="hi")


# ── envelope layer ─────────────────────────────────────────────────────────
def test_sign_refuses_empty_secret():
    with pytest.raises(ValueError):
        ENV.sign_payload(_env(), "")


def test_sign_refuses_none_secret():
    with pytest.raises(ValueError):
        ENV.sign_payload(_env(), None)


def test_verify_refuses_empty_secret():
    # A real signature must NOT validate against an empty key.
    signed = ENV.sign_payload(_env(), "real-secret")
    assert ENV.verify_signature(signed, "") is False


def test_sign_verify_roundtrip_still_works():
    signed = ENV.sign_payload(_env(), "real-secret")
    assert ENV.verify_signature(signed, "real-secret") is True


# ── backend layer ──────────────────────────────────────────────────────────
def test_backend_refuses_empty_secret():
    with pytest.raises(ValueError):
        HB.HermesBackend(agent="esther", bus_url="http://example.com",
                         bus_headers={}, secret="")


def test_backend_accepts_real_secret():
    b = HB.HermesBackend(agent="esther", bus_url="http://example.com",
                         bus_headers={}, secret="real-secret")
    assert b.secret == "real-secret"


# ── daemon wiring layer ────────────────────────────────────────────────────
def test_build_backends_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("GATEWAY_SECRET", raising=False)
    monkeypatch.delenv("CORTEX_BUS_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        DAEMON._build_backends({"backends": ["esther"]})


def test_build_backends_builds_with_secret(monkeypatch):
    monkeypatch.setenv("GATEWAY_SECRET", "real-secret")
    backends = DAEMON._build_backends({"backends": ["esther"]})
    assert "esther" in backends


def test_build_backends_skips_guard_when_no_backends(monkeypatch):
    # No backends configured → nothing signs → no secret required.
    monkeypatch.delenv("GATEWAY_SECRET", raising=False)
    assert DAEMON._build_backends({"backends": []}) == {}


def test_build_gateway_fails_closed_without_secret(monkeypatch):
    """End-to-end: a valid bot token but no GATEWAY_SECRET must not start."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1001")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "1001")
    monkeypatch.delenv("GATEWAY_SECRET", raising=False)
    with pytest.raises(SystemExit):
        DAEMON.build_gateway(EXAMPLE)


def test_build_gateway_starts_with_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("GATEWAY_SECRET", "real-secret")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1001")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "1001")
    gw = DAEMON.build_gateway(EXAMPLE)
    assert gw.backends
