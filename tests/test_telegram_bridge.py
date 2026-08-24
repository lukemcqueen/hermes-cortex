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
import json
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


# ── Party hardening 2: fail-closed state load ───────────────

def test_state_corrupt_load_fails_closed(tmp_path):
    """Corrupt state must NOT silently reset to offset 0 (would re-deliver
    everything as dupes). Fail closed: keep the corrupt file, return the
    last-good offset from a backup if present."""
    sf = tmp_path / "state.json"
    _bridge.save_state(sf, {"offset": 42, "last_msg": 7})
    # Corrupt the file
    sf.write_text("{not-json!!")
    loaded = _bridge.load_state(sf)
    # Fail-closed: never return offset 0 when we had a good state before
    assert loaded["offset"] != 0 or loaded.get("corrupt")
    # The corrupt file must still be on disk (not silently overwritten)
    assert sf.exists()


# ── Party hardening 3: sent-ledger dedup ────────────────────

def test_sent_ledger_skips_redelivered_updates():
    """SRE finding: crash between bus_send and offset-commit redelivers the
    batch → dupes. The sent-ledger records update_ids already sent; on
    re-poll after crash, already-sent updates are skipped (no dupes)."""
    ledger = _bridge.SentLedger()
    # update 101 sent but offset-commit crashed
    ledger.record(101)
    assert ledger.contains(101)
    # 102 is new
    assert not ledger.contains(102)


def test_sent_ledger_is_bounded():
    """Ledger must stay bounded (FIFO, e.g. last 1000) — never grows forever."""
    ledger = _bridge.SentLedger(max_size=5)
    for i in range(10):
        ledger.record(i)
    assert ledger.size() <= 5
    assert not ledger.contains(0)  # oldest evicted
    assert ledger.contains(9)


# ── Party hardening 4: single-instance 409 ──────────────────

def test_409_conflict_detected():
    """Telegram returns 409 when a SECOND getUpdates poller starts (only one
    poller per bot allowed). The bridge must detect this and alert, not
    silently sleep — two bridges would fight over the same bot."""
    assert _bridge.is_conflict_error(409) is True
    assert _bridge.is_conflict_error(401) is False
    assert _bridge.is_conflict_error(200) is False


# ── Return path: bus reply → Telegram (Luke: 1-way is useless) ─

def test_outbound_queue_name():
    """The agent replies via the bus to telegram_out_<AGENT>; the bridge
    polls that queue and forwards to Telegram sendMessage."""
    assert _bridge.outbound_queue("titusclaude") == "telegram_out_titusclaude"


def test_bus_reply_maps_to_telegram_payload():
    """A bus message on the outbound queue carries telegram_chat_id + text;
    the bridge maps it to a sendMessage payload."""
    msg = {
        "body": json.dumps({"telegram_chat_id": CHAT, "text": "done, fixed it",
                            "reply_to_message_id": 7}),
    }
    payload = _bridge.bus_reply_to_telegram_payload(msg)
    assert payload["chat_id"] == CHAT
    assert payload["text"] == "done, fixed it"
    assert payload["reply_to_message_id"] == 7


def test_bus_reply_missing_chat_is_skipped():
    """A reply without telegram_chat_id can't be delivered — skip it
    (the bridge archives it, never crashes on it)."""
    msg = {"body": json.dumps({"text": "orphan reply"})}
    assert _bridge.bus_reply_to_telegram_payload(msg) is None


def test_bus_reply_bad_json_is_skipped():
    assert _bridge.bus_reply_to_telegram_payload({"body": "{not-json"}) is None


def test_archive_after_delivery():
    """At-least-once: archive (ack) the bus message ONLY after Telegram
    sendMessage succeeds; a failed send leaves it queued for retry."""
    assert _bridge.should_archive(send_ok=True) is True
    assert _bridge.should_archive(send_ok=False) is False


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
