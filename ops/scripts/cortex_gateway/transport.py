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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import gateway_envelope as env

# Telegram Bot API base — functional URL lives in env (never in source,
# per the env-first rule: PII/URL gate + Luke 2026-08-24).
#
# RESOLVED AT CALL TIME, not import time (2026-10-02): an import-time constant is
# the "deploy ≠ load" bug class — env loaded after import was silently ignored,
# and a missing value produced "/botTOKEN/method" (an invalid URL) instead of an
# error. msg-gateway.py refuses to run without it; this now does the same.
def api_base() -> str:
    base = os.environ.get("TELEGRAM_API_BASE", "").strip()
    if not base:
        raise RuntimeError(
            "TELEGRAM_API_BASE is not set — refusing to build a Telegram API URL "
            "(a missing base silently yields '/bot<token>/method'). Set it in the "
            "cortex env; see ops/scripts/gateway.yaml.example.")
    return base


class PollingConflict(RuntimeError):
    """Another consumer owns this bot's getUpdates — the cutover hazard."""


TRANSIENT_HTTP = {429, 500, 502, 503, 504}
TG_MAX_CHARS = 4000          # Telegram's own limit for one text message


def chunk_body(body: str, limit: int = TG_MAX_CHARS) -> list:
    """Split a long body into sendable chunks WITHOUT losing characters.

    The incumbent chunks; the target used to truncate at 4000, silently dropping
    the tail of a long reply. Guarantee, asserted by the parity test:
    ''.join(chunk_body(b, n)) == b for every b and n > 0.

    Implementation note (learned the hard way): splitting on "\\n" and re-joining
    drops the separator at every chunk boundary. So the body is first partitioned
    into LINES WITH THEIR NEWLINES (a true partition — no character is dropped or
    duplicated), then packed greedily; a single line longer than the limit is
    hard-split as a last resort.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(body) <= limit:
        return [body]
    units = re.findall(r"[^\n]*\n|[^\n]+$", body)
    if not units:                        # empty string already returned above
        return [body]
    chunks, cur = [], ""
    for unit in units:
        if len(cur) + len(unit) <= limit:
            cur += unit
            continue
        if cur:
            chunks.append(cur)
            cur = ""
        while len(unit) > limit:         # a single monster line
            chunks.append(unit[:limit])
            unit = unit[limit:]
        cur = unit
    if cur:
        chunks.append(cur)
    return chunks


_MEDIA_KEYS = (("photo", "photo"), ("document", "document"), ("voice", "voice"),
               ("audio", "audio"), ("video", "video"), ("video_note", "video_note"),
               ("sticker", "sticker"), ("animation", "animation"))


def extract_media(msg: dict) -> list:
    """Telegram message → envelope media list.

    Each item carries a url-shaped reference plus the file id: the envelope schema
    requires `url`, and a consumer resolves it with getFile (the gateway must not
    download media inline on the poll path).
    """
    out = []
    for key, kind in _MEDIA_KEYS:
        if key not in msg:
            continue
        val = msg[key]
        item = val[-1] if isinstance(val, list) and val else val
        if not isinstance(item, dict):
            continue
        fid = item.get("file_id")
        if not fid:
            continue
        out.append({
            "url": f"tg-file://{fid}",
            "file_id": fid,
            "kind": kind,
            "file_size": item.get("file_size"),
            "mime_type": item.get("mime_type"),
            "file_name": item.get("file_name"),
        })
    return out

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

    def __init__(self, token: str, initial_offset: int = 0,
                 home_channel=None):
        # A4 fuzz hardening: fail fast on a malformed bot definition rather
        # than building a broken poller that errors at runtime.
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if isinstance(initial_offset, bool) or not isinstance(initial_offset, int):
            raise ValueError("initial_offset must be an int")
        self.token = token
        self.offset = initial_offset
        self.home_channel = home_channel

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def _api(self, method: str, params: dict, attempts: int = 4) -> dict:
        """Call the Bot API with backoff on transient failures.

        The incumbent treats a blip as recoverable; the target used to raise on the
        first non-ok response and had no retry at all (a parity gap). 429 honours
        Telegram's retry_after. A polling conflict is NOT transient — it means
        another consumer owns this bot, so it is raised as PollingConflict for the
        daemon to report rather than retried in a loop.
        """
        url = (f"{api_base()}/bot{self.token}/{method}"
               + ("?" + urllib.parse.urlencode(params) if params else ""))
        last = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(url, timeout=50) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    raise PollingConflict(
                        f"{method}: another consumer owns this bot (HTTP 409) — "
                        "stop the other poller before starting this gateway") from e
                if e.code not in TRANSIENT_HTTP:
                    raise
                if e.code == 429:
                    try:
                        payload = json.loads(e.read().decode())
                        wait = int((payload.get("parameters") or {}).get("retry_after", 0))
                    except Exception:
                        wait = 0
                    time.sleep(min(wait or 1, 30))
                else:
                    time.sleep(min(2 ** attempt, 16))
                last = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                time.sleep(min(2 ** attempt, 16))
                last = e
        raise RuntimeError(f"{method}: failed after {attempts} attempts: {last}")

    def get_updates(self, timeout: int = 30) -> list:
        params = {"timeout": timeout, "offset": self.offset}
        data = self._api("getUpdates", params)
        if not data.get("ok"):
            desc = str(data.get("description", "getUpdates failed"))
            if "conflict" in desc.lower():
                raise PollingConflict(desc)
            raise RuntimeError(desc)
        return data.get("result", [])

    # ── outbound ──
    def parse_mode(self, envelope: dict) -> str:
        """Formatting mode: the envelope wins, else TELEGRAM_PARSE_MODE, else none.

        Never hardcoded on — an unparseable payload must not cost a message, so
        send() retries plain when Telegram rejects the entities.
        """
        mode = str(envelope.get("parse_mode") or
                   os.environ.get("TELEGRAM_PARSE_MODE", "")).strip()
        return mode if mode in ("MarkdownV2", "Markdown", "HTML") else ""

    def _send_media(self, base: dict, item: dict) -> bool:
        """One attachment → sendPhoto/sendDocument. file_id or url both work."""
        ref = item.get("file_id") or item.get("url") or ""
        if not ref:
            return False
        kind = str(item.get("kind") or "document")
        if kind == "photo":
            method, key = "sendPhoto", "photo"
        else:
            method, key = "sendDocument", "document"
        params = {**base, key: ref}
        if item.get("caption"):
            params["caption"] = str(item["caption"])[:1024]
        return bool(self._api(method, params).get("ok"))

    def send(self, envelope: dict) -> bool:
        chat_id = envelope.get("channel_user_id")
        if chat_id is None:
            # Agent-initiated/proactive message with no explicit chat →
            # deliver to the home channel (TELEGRAM_HOME_CHANNEL).
            chat_id = self.home_channel
        if chat_id is None:
            raise ValueError(
                "send: envelope has no channel_user_id and "
                "TELEGRAM_HOME_CHANNEL is unset")
        base = {"chat_id": chat_id}
        if envelope.get("thread_id"):
            base["message_thread_id"] = envelope["thread_id"]

        ok = True
        for item in (envelope.get("media") or []):
            ok = self._send_media(base, item) and ok

        # CHUNKED, never truncated: the incumbent splits and the target used to
        # drop everything past 4000 chars with no error.
        mode = self.parse_mode(envelope)
        for i, chunk in enumerate(chunk_body(envelope.get("body") or "")):
            params = {**base, "text": chunk}
            if i == 0 and envelope.get("reply_to_msg_id"):
                params["reply_to_message_id"] = envelope["reply_to_msg_id"]
            if mode:
                params["parse_mode"] = mode
            data = self._api("sendMessage", params)
            if not data.get("ok") and mode:
                # Formatting must never cost a message: retry this chunk plain.
                params.pop("parse_mode", None)
                data = self._api("sendMessage", params)
            ok = bool(data.get("ok")) and ok
        return ok

    def parse(self, raw: dict) -> Optional[dict]:
        """Telegram update → envelope v1 (routing filled by the gateway).

        Parity with the incumbent's inbound surface (2026-10-02): `edited_message`
        re-dispatches, caption-only messages are not dropped, media is carried
        instead of discarded, reply linkage is preserved, and reactions/callbacks
        are forwarded as text envelopes rather than silently ignored. `tg_kind`
        records which update produced the envelope so a consumer can tell a
        reaction from a human message; the schema ignores unknown keys.
        """
        msg = raw.get("message") or raw.get("edited_message")
        if msg is None:
            # Non-message updates the incumbent also authorizes + forwards.
            if "message_reaction" in raw:
                r = raw["message_reaction"] or {}
                chat_id = (r.get("chat") or {}).get("id")
                emoji = ",".join(
                    str(x.get("emoji") or x.get("custom_emoji_id") or "?")
                    for x in (r.get("new_reaction") or [])) or "none"
                if chat_id is None:
                    return None
                return {
                    "msg_id": env.new_msg_id(), "ts": time.time(), "from_agent": "",
                    "to_agent": "", "channel": "telegram",
                    "channel_user_id": int(chat_id), "thread_id": None,
                    "body": f"[reaction: {emoji}]", "media": [],
                    "reply_to_msg_id": r.get("message_id"), "ack_required": False,
                    "tg_kind": "reaction",
                }
            if "callback_query" in raw:
                cb = raw["callback_query"] or {}
                chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
                if chat_id is None:
                    return None
                return {
                    "msg_id": env.new_msg_id(), "ts": time.time(), "from_agent": "",
                    "to_agent": "", "channel": "telegram",
                    "channel_user_id": int(chat_id), "thread_id": None,
                    "body": f"[callback: {cb.get('data') or ''}]", "media": [],
                    "reply_to_msg_id": (cb.get("message") or {}).get("message_id"),
                    "ack_required": False, "tg_kind": "callback",
                }
            return None

        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            return None
        # text OR caption — a captioned photo used to be dropped entirely.
        text = msg.get("text") or msg.get("caption") or ""
        media = extract_media(msg)
        if not text and not media:
            return None
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        return {
            "msg_id": env.new_msg_id(),
            "ts": msg.get("date", time.time()),
            "from_agent": "",
            "to_agent": "",
            "channel": "telegram",
            "channel_user_id": int(chat_id),
            "thread_id": msg.get("message_thread_id"),
            "body": text or f"[{media[0].get('kind', 'media')} attachment]",
            "media": media,
            "reply_to_msg_id": reply_to,
            "ack_required": False,
            "tg_kind": "edited" if "edited_message" in raw else "message",
        }
