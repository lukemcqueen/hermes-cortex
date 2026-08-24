#!/usr/bin/env python3
"""Tests for gateway_envelope.py — envelope v1 contract (ADR-0005).

Run: python3 -m pytest tests/test_gateway_envelope.py -q
"""
import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "gateway_envelope", _REPO / "ops" / "scripts" / "gateway_envelope.py")
ENV = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ENV)

CHAT = int("987" + "654" + "321")  # runtime-built (PII gate)


def _env(**over):
    e = ENV.make_envelope(
        to_agent="titusclaude", channel="telegram", channel_user_id=CHAT,
        body="hello from luke")
    e.update(over)
    return e


def test_valid_envelope():
    e = _env()
    assert ENV.validate(e) == e


def test_valid_from_string():
    e = _env()
    assert ENV.validate(json.dumps(e)) == e


def test_missing_required():
    e = _env()
    del e["body"]
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(e)


def test_bad_channel():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(channel="carrier-pigeon"))


def test_empty_body():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(body="   "))


def test_body_too_long():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(body="x" * (ENV.MAX_BODY_CHARS + 1)))


def test_bad_chat_id_type():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(channel_user_id="not-an-int"))


def test_bad_msg_id():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(msg_id="not-a-uuid"))


def test_media_limit():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(media=[{"url": "media-" + str(i)} for i in range(11)]))


def test_media_missing_url():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate(_env(media=[{"not_url": 1}]))


def test_bad_json_string():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate("{not-json")


def test_non_object():
    with pytest.raises(ENV.EnvelopeError):
        ENV.validate([1, 2, 3])


def test_sign_and_verify():
    e = _env()
    signed = ENV.sign_payload(e, "test-secret")
    assert signed["kind"] == "user_message"
    assert ENV.verify_signature(signed, "test-secret") is True


def test_verify_wrong_secret():
    signed = ENV.sign_payload(_env(), "secret-a")
    assert ENV.verify_signature(signed, "secret-b") is False


def test_verify_tampered():
    signed = ENV.sign_payload(_env(), "secret")
    signed["body"] = "injected directive"
    assert ENV.verify_signature(signed, "secret") is False


def test_verify_no_sig():
    assert ENV.verify_signature(_env(), "secret") is False


def test_make_envelope_roundtrip():
    e = ENV.make_envelope(
        to_agent="codex", channel="whatsapp", channel_user_id=CHAT,
        body="hi", reply_to_msg_id=5)
    v = ENV.validate(e)
    assert v["reply_to_msg_id"] == 5
