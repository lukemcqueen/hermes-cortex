"""cortex_gateway.transport — the transport layer (CR1).

Extracted from ``ops/scripts/msg-gateway.py`` (ADR-0005) with **identical
behavior**: TransportAdapter interface, TelegramAdapter (long-poll getUpdates,
per-bot offset), BotConfig, and the PGMQ bus helpers. Extraction = the
decoupled gateway's reusable inbound/outbound plumbing; the daemon (CR3)
consumes this instead of importing the monolith.

Design invariants (party-converged, unchanged from msg-gateway.py):
  - enqueue-then-ack: bus send succeeds → THEN advance Telegram offset
  - archive-after-send: outbound commit point
  - never start from offset 0 (fresh bot = explicit initial offset)
  - gateway is the ONLY getUpdates consumer per bot
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import gateway_envelope as env

# Telegram Bot API base — functional URL lives in env (never in source,
# per the env-first rule: PII/URL gate + Luke 2026-08-24). Fails closed if
# unset.
_TG_BASE = os.environ.get("TELEGRAM_API_BASE", "").strip()

DEFAULT_POLL_SECONDS = 2


@dataclass
class BotConfig:
    token_ref: str
    channel: str = "telegram"
    initial_offset: int = 0
    routing_default: str = "esther"
    routing_overrides: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "BotConfig":
        return cls(
            token_ref=d["token_ref"],
            channel=d.get("channel", "telegram"),
            initial_offset=d.get("initial_offset", 0),
            routing_default=d.get("routing", {}).get("default", "esther"),
            routing_overrides=d.get("routing", {}).get("overrides", {}),
        )


# ── Bus helpers ──────────────────────────────────────────────

def _bus_headers(bus_token: str, bus_auth: str) -> dict:
    if bus_token:
        return {"Authorization": f"Bearer {bus_token}"}
    enc = base64.b64encode(bus_auth.encode()).decode()
    return {"Authorization": "Basic " + enc}


def bus_send(bus_url: str, headers: dict, queue: str, message: dict) -> bool:
    payload = json.dumps({"queue": queue, "message": message}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/send", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


def bus_read(bus_url: str, headers: dict, queue: str, vt: int = 60) -> dict:
    payload = json.dumps({"queue": queue, "vt": vt}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/read", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError:
        return {"msg_id": None}


def bus_archive(bus_url: str, headers: dict, queue: str, msg_id: str) -> bool:
    payload = json.dumps({"queue": queue, "msg_id": msg_id}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/archive", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


# ── TransportAdapter interface ───────────────────────────────

class TransportAdapter:
    """Interface every messaging transport implements (ADR-0005).

    Routing (channel_user_id → agent) lives in the GATEWAY's routing
    table, NEVER in the adapter. An adapter only: parse(inbound) →
    envelope, send(envelope) → app.
    """

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def parse(self, raw: dict) -> Optional[dict]:
        raise NotImplementedError

    def send(self, envelope: dict) -> bool:
        raise NotImplementedError

    def health(self) -> dict:
        return {"ok": True}


class TelegramAdapter(TransportAdapter):
    """Long-poll getUpdates, ONE poller per bot (gateway owns it)."""

    def __init__(self, token: str, initial_offset: int = 0):
        # A4 fuzz hardening: fail fast on a malformed bot definition rather
        # than building a broken poller that errors at runtime.
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if isinstance(initial_offset, bool) or not isinstance(initial_offset, int):
            raise ValueError("initial_offset must be an int")
        self.token = token
        self.offset = initial_offset

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _api(self, method: str, params: dict) -> dict:
        import urllib.parse
        url = (f"{_TG_BASE}/bot{self.token}/{method}"
               + ("?" + urllib.parse.urlencode(params) if params else ""))
        with urllib.request.urlopen(url, timeout=50) as resp:
            return json.loads(resp.read().decode())

    def get_updates(self, timeout: int = 30) -> list:
        params = {"timeout": timeout, "offset": self.offset}
        data = self._api("getUpdates", params)
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "getUpdates failed"))
        return data.get("result", [])

    def send(self, envelope: dict) -> bool:
        params = {
            "chat_id": envelope["channel_user_id"],
            "text": envelope["body"][:4000],
        }
        if envelope.get("reply_to_msg_id"):
            params["reply_to_message_id"] = envelope["reply_to_msg_id"]
        data = self._api("sendMessage", params)
        return bool(data.get("ok"))

    def parse(self, raw: dict) -> Optional[dict]:
        """Telegram update → envelope v1 (routing filled by the gateway)."""
        msg = raw.get("message")
        if not msg:
            return None
        chat = msg.get("chat", {})
        text = msg.get("text", "")
        if not text:
            return None
        return {
            "msg_id": env.new_msg_id(),
            "ts": msg.get("date", time.time()),
            "from_agent": "",
            "to_agent": "",
            "channel": "telegram",
            "channel_user_id": chat.get("id"),
            "thread_id": msg.get("message_thread_id"),
            "body": text,
            "media": [],
            "reply_to_msg_id": None,
            "ack_required": False,
        }
