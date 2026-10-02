"""cortex_gateway.hermes_backend — the reference BackendAdapter (hermes).

The hermes backend is the existing decoupled mechanism: the agent consumes
``inbox_<agent>`` and replies to ``out_<agent>`` on the PGMQ bus — exactly the
flow ``msg-gateway.py`` uses today, so this adapter changes **nothing** on the
agent side while moving the gateway off the in-process loop. Swapping in pi or
steadfaste later is a different BackendAdapter against the same seam.

Contract (mirrors msg-gateway.py):
  - ``dispatch(envelope)`` → validate + HMAC-sign + ``bus_send(inbox_<agent>)``;
    returns ``None`` (hermes is async — the reply arrives via ``out_<agent>``).
  - ``poll_replies()`` → ``bus_read(out_<agent>)`` → validate →
    ``bus_archive`` (archive-after-send) → return the envelopes.
"""
from __future__ import annotations

import json
import logging
import os

import gateway_envelope as env

from . import transport as _bus
from .backend import BackendAdapter

log = logging.getLogger("cortex_gateway.backend")

# The bus requires an UPPER_CASE protocol subject on every message. This is the
# subject for "a human message arrived via the gateway" — env-overridable so a
# deployment can match its own convention without a code change.
DEFAULT_INBOUND_SUBJECT = "USER_MESSAGE"


def _extract_envelope(msg: dict):
    """The envelope inside a bus message, whichever way the bus returns it.

    Verified against the live bus 2026-10-02: `bus_read()` returns the WHOLE bus
    message under the key `body` — `{"subject": "AGENT_REPLY", "body": {<envelope>},
    "from": ..., "to": ..., "priority": ...}` — so validating `msg["body"]` directly
    failed with "missing required fields: channel, channel_user_id, msg_id, to_agent,
    ts", and poll_replies ARCHIVED the reply as malformed. A queued reply was
    therefore silently dropped: depth 1 → 0 with nothing delivered.

    Accepts both shapes: a bus message whose `body` payload is the envelope, and a
    bare envelope (a producer that sends one directly).
    """
    body = msg.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    if not isinstance(body, dict):
        return None
    # A bus-schema message around the envelope: unwrap its `body` payload.
    if "body" in body and ("subject" in body or "from" in body or "to" in body):
        inner = body.get("body")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                return None
        return inner if isinstance(inner, dict) else None
    return body


class HermesBackend(BackendAdapter):
    """Reference backend: dispatch/reply over the PGMQ bus (inbox_/out_)."""

    def __init__(self, agent: str, bus_url: str, bus_headers: dict,
                 secret: str):
        if not isinstance(agent, str) or not agent:
            raise ValueError("agent must be a non-empty string")
        if not isinstance(secret, str) or not secret:
            raise ValueError(
                "secret must be a non-empty string — an empty HMAC key "
                "yields forgeable signatures (set GATEWAY_SECRET)")
        self.agent = agent
        self.bus_url = bus_url
        self.bus_headers = bus_headers
        self.secret = secret
        # Subject for inbound human messages (the bus demands UPPER_CASE).
        self.inbound_subject = (
            os.environ.get("GATEWAY_INBOUND_SUBJECT", "").strip() or DEFAULT_INBOUND_SUBJECT)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def dispatch(self, envelope: dict):
        """Enqueue the signed inbound envelope to inbox_<agent>; async → None."""
        if not isinstance(envelope, dict):
            return None  # A4 fuzz: malformed/None inbound is a silent DLQ
        try:
            envelope = env.validate(envelope)
        except env.EnvelopeError:
            return None  # malformed inbound — DLQ, never crash the loop
        signed = env.sign_payload(envelope, self.secret)
        # The BUS has its own message schema and rejects the ADR-0005 envelope's
        # fields outright — verified against the live bus 2026-10-02:
        #   400 "unknown envelope field(s): ack_required, channel, channel_user_id,
        #        from_agent, media, msg_id, reply_to_msg_id, thread_id, to_agent, ts.
        #        Allowed fields: body, correlation_id, forwarded_from, from,
        #        priority, subject, timestamp, to, type"
        # and `from` must match the authenticated agent ("from 'gateway' does not
        # match authenticated agent 'esther'"). So the signed envelope travels as
        # the message BODY — which is also exactly how poll_replies() reads a
        # reply back (it json-decodes `body` into an envelope). Sending the bare
        # envelope meant EVERY dispatch was a 400 and no human message ever
        # reached an agent, which /status could not reveal because it never
        # touches the bus.
        message = {
            "subject": self.inbound_subject,
            "body": json.dumps(signed),
            "from": self.agent,
            "to": self.agent,
            "priority": 0,
            "correlation_id": str(envelope.get("msg_id", "")),
        }
        ok = _bus.bus_send(self.bus_url, self.bus_headers,
                           f"inbox_{self.agent}", message)
        if not ok:
            # A FAILED enqueue used to be swallowed (`_ = ok`) — the message vanished
            # with no log, no error and an offset that still advanced, so a mis-routed
            # agent name (e.g. the example config's placeholder "hermes", which has no
            # queue) silently dropped every human message. Found by the cutover rehearsal
            # 2026-10-02: /status worked (it never touches the bus) while a normal message
            # went nowhere. Visibility is the minimum; the daemon's offset still advances,
            # so this is logged as a WARNING rather than pretended to be handled.
            log.warning(
                "dispatch FAILED for agent %s: could not enqueue to inbox_%s "
                "(bus=%s). The inbound message was NOT delivered — check that the "
                "agent name matches a real queue (e.g. 'esther' → inbox_esther).",
                self.agent, self.agent, self.bus_url)
        # Async: never a synchronous reply. A failed enqueue surfaces as None
        # too (the daemon's enqueue-then-ack treats None dispatch + False send
        # identically to a silent backend for offset purposes).
        return None

    def poll_replies(self, max_n: int = 5) -> list:
        """Drain out_<agent> replies; archive-after-send; return envelopes."""
        out = []
        for _ in range(max_n):
            msg = _bus.bus_read(self.bus_url, self.bus_headers,
                                f"out_{self.agent}", vt=60)
            if not msg or not msg.get("msg_id"):
                break
            body = _extract_envelope(msg)
            try:
                envelope = env.validate(body or {})
            except env.EnvelopeError:
                _bus.bus_archive(self.bus_url, self.bus_headers,
                                 f"out_{self.agent}", msg["msg_id"])
                continue
            out.append(envelope)
            _bus.bus_archive(self.bus_url, self.bus_headers,
                             f"out_{self.agent}", msg["msg_id"])
        return out

    def health(self) -> dict:
        return {"ok": True, "backend": "hermes", "agent": self.agent}
