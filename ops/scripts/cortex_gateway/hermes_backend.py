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

import gateway_envelope as env

from . import transport as _bus
from .backend import BackendAdapter


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
        ok = _bus.bus_send(self.bus_url, self.bus_headers,
                           f"inbox_{self.agent}", signed)
        # Async: never a synchronous reply. A failed enqueue surfaces as None
        # too (the daemon's enqueue-then-ack treats None dispatch + False send
        # identically to a silent backend for offset purposes).
        _ = ok
        return None

    def poll_replies(self, max_n: int = 5) -> list:
        """Drain out_<agent> replies; archive-after-send; return envelopes."""
        out = []
        for _ in range(max_n):
            msg = _bus.bus_read(self.bus_url, self.bus_headers,
                                f"out_{self.agent}", vt=60)
            if not msg or not msg.get("msg_id"):
                break
            body = msg.get("body")
            if isinstance(body, str):
                try:
                    import json
                    body = json.loads(body)
                except ValueError:
                    body = None
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
