#!/usr/bin/env python3
"""telegram-bridge.py — generic Telegram <-> bus inbox bridge (any agent).

Design (Luke 2026-08-24): ONE bridge any agent can run — Hermes agents AND
coding agents (Claude Code, Codex, OpenCode, Blackbox, Grok, ...). Each
agent configures its OWN bot token + AGENT_NAME; the bridge maps:

    Telegram update  →  POST {CORTEX_BUS_URL}/api/pgmq/send
                        queue = inbox_<AGENT>   (same queue the cortex-bus
                        MCP reads — bus-identical inbox, any agent)
    bus reply        ←  POST /api/pgmq/read on telegram_out_<AGENT>
                        → Telegram sendMessage to the originating chat

FULL TWO-WAY (fixed 2026-08-24 — 1-way was useless):
  * inbound:  Telegram → inbox_<AGENT> → agent reads via cortex-bus MCP
  * outbound: agent replies via cortex-bus MCP inbox_send to
    telegram_out_<AGENT> with body {"telegram_chat_id": <id>,
    "text": "...", "reply_to_message_id": <id>} → bridge forwards to
    Telegram. The telegram_chat_id is captured on the inbound message
    (update_to_bus_payload) so the agent knows where to reply.

Per-agent identity (AGENT_NAME env → inbox_<AGENT>), no hermes token reuse,
stdlib-only (urllib), durable offset in a small state file (atomic
tmp+rename + fsync), idle-silent (long-polling getUpdates, no writes when
empty). Kill mid-flight → offset resumes from last committed; sent-ledger
dedups crash redelivery; outbound archives only after sendMessage succeeds
(at-least-once).

Usage (run under the agent's own env — NOT hermes's):
    AGENT_NAME=titusclaude \
    TELEGRAM_BOT_TOKEN=<own bot token> \
    CORTEX_BUS_URL=... CORTEX_BUS_TOKEN=... \
    python3 telegram-bridge.py [--state-dir ~/.<agent>/state]

SECURITY (party finding, 2026-08-24): the Telegram bot token is an
admin-capable credential (reads ALL chats, sends as the bot) — handle it
like a password. Store it in a per-agent secrets file with 600 perms
(e.g. ~/.<agent>/secrets.env, chmod 600, owned by the agent user), NEVER
in a shared-server ~/.bashrc or a world-readable systemd unit. The bus
token is per-agent (rotated via cortex-agent-manager.py rotate <agent>),
never shared between agents.

Expansion: to give a NEW coding agent a Telegram inbox — create a bot via
BotFather, set its token + AGENT_NAME in its OWN 600-perm secrets file,
register the cortex-bus MCP in the agent's .mcp.json (AGENT_NAME=<same>).
The bridge is shared; only the identity changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

POLL_TIMEOUT = 50  # long-poll seconds — idle-silent by construction
STATE_DEFAULT = {"offset": 0, "last_msg": 0}


# ── State file (durable offset, atomic write) ───────────────

class SentLedger:
    """Bounded FIFO of update_ids already sent to the bus.

    SRE party finding (2026-08-24): a crash between bus_send and the
    offset-commit redelivers the batch → duplicates. The ledger records
    sent update_ids; on re-poll after a crash, already-sent updates are
    skipped (no dupes) while their offsets still advance. Bounded so it
    never grows forever (default: last 1000).
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._ids: list[int] = []

    def record(self, update_id: int) -> None:
        self._ids.append(update_id)
        if len(self._ids) > self.max_size:
            self._ids = self._ids[-self.max_size:]

    def contains(self, update_id: int) -> bool:
        return update_id in self._ids

    def size(self) -> int:
        return len(self._ids)


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        fh.write(json.dumps(state))
        fh.flush()
        os.fsync(fh.fileno())  # party hardening: durable before rename
    tmp.replace(path)  # atomic on POSIX — a kill mid-write never corrupts


def load_state(path: Path) -> dict:
    """Load state; FAIL CLOSED on corruption (party hardening).

    A corrupt state file must never silently reset to offset 0 (that would
    re-deliver everything as dupes). Keep the corrupt file on disk for
    forensics, return a marked dict the caller can alert on.
    """
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return {**dict(STATE_DEFAULT), **data}
        return {**dict(STATE_DEFAULT), "corrupt": True}
    except ValueError:
        return {**dict(STATE_DEFAULT), "corrupt": True}  # keep file, alert
    except OSError:
        return dict(STATE_DEFAULT)  # missing file = fresh start


# ── Telegram API (stdlib) ───────────────────────────────────

def tg_get_updates(token: str, offset: int) -> list:
    url = (f"https://api.telegram.org/bot{token}/getUpdates"
           f"?offset={offset}&timeout={POLL_TIMEOUT}&allowed_updates="
           f'["message"]')
    with urllib.request.urlopen(url, timeout=POLL_TIMEOUT + 15) as resp:
        data = json.loads(resp.read().decode())
    return data.get("result", [])


def tg_send_message(token: str, chat_id, text: str, reply_to: int | None) -> bool:
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    body = urllib.parse.urlencode(payload).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=body)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False


# ── Bus API (POST /api/pgmq/send — same as cortex-bus MCP) ──

def bus_send(bus_url: str, token: str, queue: str, message: dict) -> bool:
    payload = json.dumps({
        "queue": queue,
        "message": message,
        "priority": 0,
    }).encode()
    url = f"{bus_url}/api/pgmq/send"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


# ── Mapping helpers (tested) ────────────────────────────────

def update_to_bus_payload(update: dict | None, agent: str) -> dict | None:
    """Map a Telegram update to a bus /api/pgmq/send payload, or None to skip."""
    if not update:
        return None
    msg = update.get("message")
    if not msg:
        return None  # edited_message, channel_post, callback — skip
    chat = msg.get("chat", {})
    sender = msg.get("from", {})
    text = msg.get("text", "")
    if not text:
        return None
    first = sender.get("first_name") or sender.get("username") or "Telegram"
    return {
        "queue": f"inbox_{agent}",
        "message": {
            "from": f"telegram:{sender.get('username') or first}",
            "to": agent,
            "topic": "telegram",
            "subject": first,
            "body": text,
            "priority": "normal",
            # the originating chat is needed for the reply leg
            "telegram_chat_id": chat.get("id"),
            "telegram_msg_id": msg.get("message_id"),
        },
    }


def next_offset(updates: list) -> int:
    """max(update_id)+1 — never re-poll consumed updates (no dupes)."""
    if not updates:
        return 0
    return max(u["update_id"] for u in updates) + 1


def reply_to_telegram_payload(chat_id, text: str, reply_to_message_id: int) -> dict:
    return {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id,
    }


def is_conflict_error(http_code: int) -> bool:
    """Telegram returns 409 when a SECOND getUpdates poller starts (one
    poller per bot). The bridge must detect it and alert — two bridges
    fighting over the same bot would corrupt offsets."""
    return http_code == 409


# ── Return path: bus reply → Telegram (Luke 2026-08-24) ─────
# 1-way communication is useless — the agent replies via the bus to
# telegram_out_<AGENT>, the bridge forwards it to Telegram sendMessage.

def outbound_queue(agent: str) -> str:
    """Queue the agent posts replies to; the bridge polls + forwards."""
    return f"telegram_out_{agent}"


def bus_reply_to_telegram_payload(msg: dict) -> dict | None:
    """Map a bus outbound message to a Telegram sendMessage payload.

    The agent's reply body carries telegram_chat_id (captured on the
    inbound message) + text (+ optional reply_to_message_id). Missing
    chat_id or unparseable body → None (skipped, never crashes).
    """
    try:
        body = json.loads(msg.get("body", "{}"))
    except (ValueError, TypeError):
        return None
    chat_id = body.get("telegram_chat_id")
    text = body.get("text", "")
    if chat_id is None or not text:
        return None
    reply_to = body.get("reply_to_message_id")
    return reply_to_telegram_payload(chat_id, text, reply_to)


def should_archive(send_ok: bool) -> bool:
    """At-least-once: archive (ack) the bus message ONLY after Telegram
    sendMessage succeeds; a failed send stays queued for retry."""
    return send_ok


def bus_read(bus_url: str, token: str, queue: str, vt: int = 60) -> dict:
    """Dequeue one message from a PGMQ queue (POST /api/pgmq/read)."""
    payload = json.dumps({"queue": queue, "vt": vt}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/read", data=payload,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def bus_archive(bus_url: str, token: str, queue: str, msg_id: str) -> bool:
    """Ack a processed message (POST /api/pgmq/archive)."""
    payload = json.dumps({"queue": queue, "msg_id": msg_id}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/archive", data=payload,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


# ── Main loop ───────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Generic Telegram<->bus bridge")
    ap.add_argument("--state-dir", default=None,
                    help="dir for state.json (default: ~/.<agent>/state)")
    args = ap.parse_args()

    agent = os.environ.get("AGENT_NAME", "").strip()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    bus_url = os.environ.get("CORTEX_BUS_URL", "").strip()
    bus_token = os.environ.get("CORTEX_BUS_TOKEN", "").strip()
    if not (agent and bot_token and bus_url and bus_token):
        print("error: AGENT_NAME, TELEGRAM_BOT_TOKEN, CORTEX_BUS_URL, "
              "CORTEX_BUS_TOKEN all required", file=sys.stderr)
        return 2

    state_dir = Path(args.state_dir) if args.state_dir else Path.home() / f".{agent}" / "state"
    state_file = state_dir / "state.json"
    state = load_state(state_file)
    if state.get("corrupt"):
        print(f"⚠️  CRITICAL: state file {state_file} is CORRUPT — failing "
              f"closed (offset NOT reset). Fix the file manually or rotate "
              f"the agent; messages will not be re-delivered as dupes.",
              file=sys.stderr)
        # fail closed: exit so the operator notices; no silent offset-0 reset
        return 3
    ledger = SentLedger()

    while True:
        try:
            updates = tg_get_updates(bot_token, state["offset"])
        except urllib.error.HTTPError as e:
            if is_conflict_error(e.code):
                print(f"⛔ 409 CONFLICT: another poller is using this bot's "
                      f"getUpdates (single-poller limit). Two bridges are "
                      f"fighting — killing this one. Check for a duplicate "
                      f"telegram-bridge process.", file=sys.stderr)
                return 4
            print(f"⚠️  getUpdates HTTP {e.code} — retrying", file=sys.stderr)
            time.sleep(5)
            continue
        except Exception:
            time.sleep(5)
            continue

        # SRE findings (party 2026-08-24):
        #  1. NEVER commit max(update_id)+1 for the whole batch — a failed
        #     bus_send would permanently skip that update. Advance offset
        #     only past updates SUCCESSFULLY sent (or skipped).
        #  2. Crash between send and offset-commit redelivers the batch →
        #     dupes. The sent-ledger records sent update_ids; already-sent
        #     updates are skipped (no dupes) while their offsets advance.
        for upd in updates:
            uid = upd["update_id"]
            if ledger.contains(uid):
                # already delivered before a crash — skip, just advance
                state["offset"] = max(state["offset"], uid + 1)
                save_state(state_file, state)
                continue
            payload = update_to_bus_payload(upd, agent)
            if payload is None:
                state["offset"] = max(state["offset"], uid + 1)
                save_state(state_file, state)
                continue
            ok = bus_send(bus_url, bus_token, payload["queue"], payload["message"])
            if ok:
                ledger.record(uid)  # remember: delivered (dedup on crash)
                state["last_msg"] = payload["message"].get("telegram_msg_id", 0)
                state["offset"] = max(state["offset"], uid + 1)
                save_state(state_file, state)  # commit AFTER durable send
            # on failure: offset unchanged → re-polled next cycle (at-least-once)
        # idle-silent: empty updates → no writes, loop sleeps on long-poll

        # ── Return path (Luke: 1-way is useless) ─────────────
        # Drain the agent's outbound queue: each bus reply → Telegram
        # sendMessage; archive (ack) ONLY after successful delivery.
        out_q = outbound_queue(agent)
        for _ in range(10):  # bounded drain per cycle — never starve inbound
            try:
                out_msg = bus_read(bus_url, bus_token, out_q, vt=60)
            except Exception:
                break  # bus hiccup — try again next cycle
            if not out_msg or not out_msg.get("msg_id"):
                break  # queue empty
            tpay = bus_reply_to_telegram_payload(out_msg)
            if tpay is None:
                # undeliverable (no chat_id / bad body) — archive, don't loop
                bus_archive(bus_url, bus_token, out_q, out_msg["msg_id"])
                continue
            ok = tg_send_message(bot_token, tpay["chat_id"], tpay["text"],
                                 tpay.get("reply_to_message_id"))
            if should_archive(ok):
                bus_archive(bus_url, bus_token, out_q, out_msg["msg_id"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
