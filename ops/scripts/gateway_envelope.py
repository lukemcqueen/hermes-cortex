#!/usr/bin/env python3
"""Envelope v1 — the messaging-gateway message contract (ADR-0005).

Any producer/consumer that speaks HTTP POST/GET on inbox_<AGENT>/
out_<AGENT> with this schema works — Hermes, Claude Code, Codex, future
agents — no gateway changes. The gateway validates at both boundaries and
DLQs malformed messages.

Schema v1:
    {
      "msg_id": "uuid",
      "ts": "ISO-8601",
      "from_agent": "esther",           # optional; set by sender
      "to_agent": "titusclaude",        # required; routing target
      "channel": "telegram",            # required; app transport
      "channel_user_id": <int>,         # required; sender's chat id
      "thread_id": null,                # optional; group/thread
      "body": "text",                   # required; the message
      "media": [],                      # optional; attachment list
      "reply_to_msg_id": null,          # optional; thread reply
      "ack_required": false,            # optional; read-receipt ask
    }

Security (party, Security 5/10): inbound app text is UNTRUSTED. Agents
accept only gateway-signed messages as DATA (kind=user_message), never
directives. This module validates shape only; signing lives in the
gateway.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

VERSION = 1
REQUIRED = {"msg_id", "ts", "to_agent", "channel", "channel_user_id", "body"}
CHANNELS = {"telegram", "whatsapp", "matrix", "signal", "sms"}
MAX_BODY_CHARS = 10000
MAX_MEDIA = 10


class EnvelopeError(ValueError):
    """Raised on schema violations — the gateway DLQs these."""


def new_msg_id() -> str:
    return str(uuid.uuid4())


def make_envelope(to_agent: str, channel: str, channel_user_id: int,
                  body: str, from_agent: str = "", thread_id=None,
                  reply_to_msg_id=None, media=None,
                  ack_required: bool = False) -> dict:
    """Build a valid envelope v1 (used by the gateway's adapters)."""
    import datetime as _dt
    return {
        "msg_id": new_msg_id(),
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "thread_id": thread_id,
        "body": body,
        "media": media or [],
        "reply_to_msg_id": reply_to_msg_id,
        "ack_required": ack_required,
    }


def validate(data: dict | str) -> dict:
    """Validate an envelope; raise EnvelopeError on violation, return it."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as e:
            raise EnvelopeError(f"not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise EnvelopeError("envelope must be a JSON object")

    missing = REQUIRED - set(data)
    if missing:
        raise EnvelopeError(f"missing required fields: {sorted(missing)}")

    if data["channel"] not in CHANNELS:
        raise EnvelopeError(
            f"channel '{data['channel']}' not in {sorted(CHANNELS)}")

    if not isinstance(data["body"], str) or not data["body"].strip():
        raise EnvelopeError("body must be a non-empty string")
    if len(data["body"]) > MAX_BODY_CHARS:
        raise EnvelopeError(
            f"body too long ({len(data['body'])} > {MAX_BODY_CHARS})")

    if not isinstance(data["channel_user_id"], int):
        raise EnvelopeError("channel_user_id must be an int")

    try:
        uuid.UUID(str(data["msg_id"]))
    except ValueError:
        raise EnvelopeError(f"msg_id not a UUID: {data['msg_id']}")

    media = data.get("media") or []
    if not isinstance(media, list) or len(media) > MAX_MEDIA:
        raise EnvelopeError(f"media must be a list ≤ {MAX_MEDIA}")
    for m in media:
        if not isinstance(m, dict) or "url" not in m:
            raise EnvelopeError(f"media item must have a url: {m!r}")

    return data


def sign_payload(envelope: dict, secret: str) -> dict:
    """HMAC-sign an inbound envelope (gateway side) — agents verify.

    The signature marks the message as gateway-originated (DATA, not
    directives). Agents MUST verify before trusting human text.
    """
    import hashlib
    import hmac as _hmac
    canonical = json.dumps(
        {k: envelope.get(k) for k in sorted(envelope)}, sort_keys=True,
        default=str)
    sig = _hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {**envelope, "gateway_sig": sig, "kind": "user_message"}


def verify_signature(envelope: dict, secret: str) -> bool:
    """Agent side: verify a gateway-signed envelope (constant-time)."""
    import hashlib
    import hmac as _hmac
    sig = envelope.get("gateway_sig", "")
    if not sig:
        return False
    # kind is gateway-added metadata (user_message marker), not signed
    # content — strip it along with the signature itself.
    unsigned = {k: v for k, v in envelope.items()
                if k not in ("gateway_sig", "kind")}
    canonical = json.dumps(unsigned, sort_keys=True, default=str)
    expect = _hmac.new(secret.encode(), canonical.encode(),
                       hashlib.sha256).hexdigest()
    return _hmac.compare_digest(sig, expect)
