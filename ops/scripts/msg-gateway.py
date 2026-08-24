#!/usr/bin/env python3
"""msg-gateway.py — the unified Messaging Gateway (ADR-0005, MVP).

ONE daemon per server owns ALL messaging app connections. Deterministic
plumbing: poll → translate → route → send. No LLM, no memory, no inbox of
its own — bus identity only (gateway_<host> principal).

MVP scope (Product party ordering, step 1):
  - TransportAdapter interface (start/stop/parse/send/health)
  - Telegram adapter (long-poll getUpdates, per-bot offset, enqueue-then-ack)
  - Routing table (gateway.yaml): channel_user_id → AGENT_NAME
  - Envelope v1 validation + HMAC signing (gateway_envelope.py)

Design invariants (party-converged):
  - enqueue-then-ack: bus send succeeds → THEN advance Telegram offset
  - archive-after-send: outbound commit point
  - never start from offset 0 (fresh bot = explicit initial offset)
  - gateway is the ONLY getUpdates consumer per bot

Usage:
    AGENT_NAME=gw-<host> GATEWAY_CONFIG=gateway.yaml python3 msg-gateway.py

Config (gateway.yaml):
    secret: <hmac-signing-secret>      # signs inbound (agents verify)
    bus_url: <bus base>                # or env CORTEX_BUS_URL
    bus_auth: agent:pass               # or env CORTEX_BUS_AUTH
    bots:
      - token_ref: TELEGRAM_BOT_TOKEN_1
        channel: telegram
        initial_offset: 0
        routing:
          default: esther
          overrides:
            <chat_id>: codex
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import gateway_envelope as env

# Telegram Bot API base — functional URL lives in env (never in source,
# per the env-first rule: PII/URL gate + Luke 2026-08-24). The gateway
# fails closed if unset.
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
    import base64
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


# ── Gateway ──────────────────────────────────────────────────

class Gateway:
    def __init__(self, config_path: Path, bus_url: str, bus_headers: dict,
                 secret: str):
        self.config_path = config_path
        self.bus_url = bus_url
        self.bus_headers = bus_headers
        self.secret = secret
        self.bots: list = []
        self.adapters: dict = {}
        self.offsets: dict = {}

    def load_config(self) -> None:
        data = json.loads(self.config_path.read_text())
        self.bots = [BotConfig.from_dict(b) for b in data.get("bots", [])]
        for b in self.bots:
            token = os.environ.get(b.token_ref, "")
            if not token:
                print(f"error: {b.token_ref} not set in env", file=sys.stderr)
                sys.exit(2)
            self.adapters[b.token_ref] = TelegramAdapter(token, b.initial_offset)
            self.offsets[b.token_ref] = b.initial_offset

    def route(self, bot: BotConfig, chat_id) -> str:
        if chat_id is not None and str(chat_id) in bot.routing_overrides:
            return str(bot.routing_overrides[str(chat_id)])
        return bot.routing_default

    def ingest(self, bot: BotConfig, raw: dict) -> bool:
        """One app event → validate → route → sign → enqueue-then-ack."""
        adapter = self.adapters[bot.token_ref]
        envelope = adapter.parse(raw)
        if envelope is None:
            return True
        envelope["to_agent"] = self.route(bot, envelope["channel_user_id"])
        try:
            envelope = env.validate(envelope)
        except env.EnvelopeError as e:
            print(f"⚠️  DLQ malformed envelope: {e}", file=sys.stderr)
            return True
        signed = env.sign_payload(envelope, self.secret)
        ok = bus_send(self.bus_url, self.bus_headers,
                      f"inbox_{envelope['to_agent']}", signed)
        if not ok:
            return False  # enqueue-then-ack: DON'T advance offset
        return True

    def poll_bot(self, bot: BotConfig) -> None:
        adapter = self.adapters[bot.token_ref]
        try:
            updates = adapter.get_updates(timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                print(f"⛔ 409 on {bot.token_ref}: ANOTHER poller is using "
                      f"this bot. Advisory lock should prevent this — check "
                      f"for a second gateway/legacy adapter.", file=sys.stderr)
                raise SystemExit(4)
            print(f"⚠️  getUpdates HTTP {e.code} on {bot.token_ref}",
                  file=sys.stderr)
            return
        except Exception as e:
            print(f"⚠️  poll error {bot.token_ref}: {e}", file=sys.stderr)
            return

        for upd in updates:
            uid = upd.get("update_id")
            if uid is None:
                continue
            if self.ingest(bot, upd):
                self.offsets[bot.token_ref] = max(
                    self.offsets[bot.token_ref], uid + 1)
                adapter.offset = self.offsets[bot.token_ref]

    def drain_outbound(self) -> None:
        agents = {b.routing_default for b in self.bots}
        for b in self.bots:
            agents.update(b.routing_overrides.values())
        for agent in agents:
            queue = f"out_{agent}"
            for _ in range(5):
                msg = bus_read(self.bus_url, self.bus_headers, queue, vt=60)
                if not msg or not msg.get("msg_id"):
                    break
                # The bus returns body as a dict (envelope object); accept
                # both dict and JSON-string shapes (live-test finding).
                body = msg.get("body")
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except ValueError:
                        body = None
                try:
                    envelope = env.validate(body or {})
                except env.EnvelopeError:
                    bus_archive(self.bus_url, self.bus_headers, queue,
                                msg["msg_id"])
                    continue
                adapter = self._adapter_for(envelope)
                if adapter is None:
                    bus_archive(self.bus_url, self.bus_headers, queue,
                                msg["msg_id"])
                    continue
                ok = adapter.send(envelope)
                if ok:
                    bus_archive(self.bus_url, self.bus_headers, queue,
                                msg["msg_id"])

    def _adapter_for(self, envelope: dict) -> Optional[TransportAdapter]:
        for b in self.bots:
            if b.channel == envelope["channel"]:
                return self.adapters[b.token_ref]
        return None

    def run_once(self) -> None:
        for b in self.bots:
            self.poll_bot(b)
        self.drain_outbound()

    def run_outbound_only(self) -> None:
        """Outbound-only: drain out_<AGENT> → app; NO getUpdates.

        Use when another poller (e.g. the Hermes gateway) already owns the
        bot's inbound (Telegram single-poller limit — 409 otherwise).
        """
        while True:
            self.drain_outbound()
            time.sleep(DEFAULT_POLL_SECONDS)

    def run_locked(self) -> None:
        """run() with per-bot advisory locks (SRE: 409-avoidance, cutover,
        multi-server active-passive in one mechanism).

        A bot whose lock is held elsewhere is skipped (standby) — the
        gateway never double-polls a bot.
        """
        import bot_locks
        while True:
            for b in self.bots:
                key = bot_locks.bot_key(b.token_ref, b.channel)
                with bot_locks.BotLock(bot_locks._connect, key) as acquired:
                    if not acquired:
                        print(f"⏸️  bot {b.token_ref}: lock held by another "
                              f"gateway — standby (not polling)",
                              file=sys.stderr)
                        continue
                    self.poll_bot(b)
            self.drain_outbound()
            time.sleep(DEFAULT_POLL_SECONDS)


# ── CLI ──────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Unified Messaging Gateway")
    ap.add_argument("--config", default="gateway.yaml")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--outbound-only", action="store_true",
                    help="drain out_<AGENT> → app only; no getUpdates "
                         "(another poller owns inbound)")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"error: config {cfg_path} not found", file=sys.stderr)
        return 2
    data = json.loads(cfg_path.read_text())

    bus_url = data.get("bus_url") or os.environ.get("CORTEX_BUS_URL", "")
    bus_token = os.environ.get("CORTEX_BUS_TOKEN", "")
    bus_auth = (data.get("bus_auth") or os.environ.get("CORTEX_BUS_AUTH", "")
                or os.environ.get("CORTEX_BASIC_AUTH", ""))
    if not bus_url or not (bus_token or bus_auth):
        print("error: bus_url + bus_token/bus_auth required", file=sys.stderr)
        return 2
    secret = data.get("secret") or os.environ.get("GATEWAY_SECRET", "")
    if not secret:
        print("error: secret required (HMAC signing)", file=sys.stderr)
        return 2
    if not _TG_BASE:
        print("error: TELEGRAM_API_BASE required in env (functional URL "
              "lives in .env, never in source)", file=sys.stderr)
        return 2

    gw = Gateway(cfg_path, bus_url, _bus_headers(bus_token, bus_auth), secret)
    gw.load_config()
    if args.once:
        gw.run_once()
    elif args.outbound_only:
        gw.run_outbound_only()  # Hermes gateway owns inbound
    else:
        gw.run_locked()  # per-bot advisory locks (safe default)
    return 0


if __name__ == "__main__":
    sys.exit(main())
