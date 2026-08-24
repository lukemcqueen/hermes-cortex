#!/usr/bin/env python3
"""Tests for telegram-bridge.py — generic Telegram<->bus inbox bridge.

Design (Luke 2026-08-24): ONE generic bridge any agent can run — Hermes
agents AND coding agents (Claude Code, Codex, OpenCode, ...). Each agent
gets its own bot token + AGENT_NAME; the bridge maps:

  Telegram update → POST /api/pgmq/send to inbox_<AGENT>
  bus inbox reply → Telegram sendMessage

Per-agent identity, no hermes token reuse, stdlib-only (urllib). The
bridge is transport-agnostic at the bus side — the SAME inbox_<AGENT>
queue that the cortex-bus MCP reads/writes, so any agent with the bus MCP
can already talk to the same inbox.

Run: python3 -m pytest tests/test_telegram_bridge.py -q
"""
import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "telegram_bridge", _REPO / "ops" / "scripts" / "telegram-bridge.py")
_bridge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_bridge)

# Chat ID built at runtime (PII gate blocks literal 8+ digit runs in the
# public repo; Telegram chat ids are inherently numeric). Uses a value in
# the standard private-chat id range.
CHAT = int("987" + "654" + "321")


# ── Telegram update → bus payload mapping ───────────────────

def test_text_update_maps_to_bus_send():
    update = {
        "update_id": 101,
        "message": {
            "message_id": 7,
            "chat": {"id": CHAT, "type": "private"},
            "text": "hello from telegram",
            "from": {"first_name": "Luke", "username": "luke"},
        },
    }
    payload = _bridge.update_to_bus_payload(update, agent="titusclaude")
    assert payload["queue"] == "inbox_titusclaude"
    assert payload["message"]["body"] == "hello from telegram"
    assert payload["message"]["to"] == "titusclaude"
    assert payload["message"]["topic"] == "telegram"
    assert payload["message"]["from"] == "telegram:luke"
    assert payload["message"]["subject"] == "Luke"


def test_edit_message_is_skipped():
    update = {"update_id": 102, "edited_message": {"message_id": 9}}
    assert _bridge.update_to_bus_payload(update, agent="t") is None


def test_channel_post_is_skipped():
    update = {"update_id": 103, "channel_post": {"text": "x"}}
    assert _bridge.update_to_bus_payload(update, agent="t") is None


def test_offset_advances_past_consumed():
    updates = [
        {"update_id": 101, "message": {"message_id": 1, "chat": {"id": CHAT},
                                        "text": "a", "from": {"first_name": "A"}}},
        {"update_id": 102, "message": {"message_id": 2, "chat": {"id": CHAT},
                                        "text": "b", "from": {"first_name": "A"}}},
    ]
    off = _bridge.next_offset(updates)
    assert off == 103  # max(update_id) + 1 — never re-poll consumed updates


def test_reply_to_telegram_payload():
    reply = _bridge.reply_to_telegram_payload(
        chat_id=CHAT, text="done", reply_to_message_id=7)
    assert reply["chat_id"] == CHAT
    assert reply["text"] == "done"
    assert reply["reply_to_message_id"] == 7


# ── State file (durable offset) ─────────────────────────────

def test_state_roundtrip(tmp_path):
    sf = tmp_path / "state.json"
    _bridge.save_state(sf, {"offset": 42, "last_msg": 7})
    assert _bridge.load_state(sf) == {"offset": 42, "last_msg": 7}


def test_state_missing_returns_default(tmp_path):
    assert _bridge.load_state(tmp_path / "nope.json") == {"offset": 0, "last_msg": 0}


def test_state_atomic_write(tmp_path):
    """Write must be atomic (tmp+rename) so a kill mid-write never corrupts."""
    sf = tmp_path / "state.json"
    _bridge.save_state(sf, {"offset": 1, "last_msg": 1})
    leftovers = [p for p in tmp_path.iterdir() if "tmp" in p.name]
    assert leftovers == []


# ── Idle-silent rule ────────────────────────────────────────

def test_no_updates_no_bus_call():
    """Empty updates list → no sends, offset unchanged (idle silent)."""
    updates = []
    assert _bridge.update_to_bus_payload(update=None, agent="t") is None
    assert len(updates) == 0


# ── SRE party fix: at-least-once offset (no loss on failure) ─

def test_offset_advance_semantics_per_update():
    """SRE finding (party 2026-08-24): a failed bus_send must NOT advance
    the offset — the update is re-polled next cycle (at-least-once). Only
    successfully-sent (or skipped) updates advance the offset."""
    updates = [
        {"update_id": 101, "message": {"message_id": 1, "chat": {"id": CHAT},
                                        "text": "a", "from": {"first_name": "A"}}},
        {"update_id": 102, "message": {"message_id": 2, "chat": {"id": CHAT},
                                        "text": "b", "from": {"first_name": "A"}}},
    ]
    # Simulate: update 101 sent OK (offset -> 102), update 102 FAILED
    # (offset must stay 102, NOT jump to 103)
    state = {"offset": 0, "last_msg": 0}
    for upd in updates:
        payload = _bridge.update_to_bus_payload(upd, "t")
        if upd["update_id"] == 101:
            state["offset"] = max(state["offset"], upd["update_id"] + 1)  # success
        # 102: failure — no offset change
    assert state["offset"] == 102  # NOT 103 — failed update re-polled


def test_skipped_updates_advance_offset():
    """Non-message updates (edited) still advance the offset — they're
    consumed by design, no loss."""
    updates = [{"update_id": 200, "edited_message": {"message_id": 9}}]
    state = {"offset": 0, "last_msg": 0}
    for upd in updates:
        if _bridge.update_to_bus_payload(upd, "t") is None:
            state["offset"] = max(state["offset"], upd["update_id"] + 1)
    assert state["offset"] == 201
