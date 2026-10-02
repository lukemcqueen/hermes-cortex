#!/usr/bin/env python3
"""Approval flow (parity slice 2): inline keyboards, callbacks, message edits.

The incumbent can put buttons on a message and receive the press. That needs four wires, and
all four are asserted here: buttons render on the LAST chunk of a reply, a malformed button
never costs the message, a press is answered (so the user's spinner clears) and carries the
query id, and an already-sent message can be rewritten (approval outcome, streaming).
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import daemon as D          # noqa: E402
from cortex_gateway import transport as T       # noqa: E402

CHAT = 100001


def _adapter(fail=False):
    a = T.TelegramAdapter(token="t", home_channel=None)
    calls = []

    def _api(method, params, *args, **kwargs):
        calls.append({"method": method, "params": dict(params)})
        if fail:
            raise RuntimeError("Telegram refused")
        return {"ok": True, "result": {"message_id": 5}}

    a._api = _api
    return a, calls


def test_buttons_render_on_the_last_chunk():
    a, calls = _adapter()
    a.send({"channel_user_id": CHAT, "body": "Approve this change?",
            "buttons": [[{"text": "Approve", "data": "approve"},
                         {"text": "Reject", "data": "reject"}]]})
    assert calls[-1]["method"] == "sendMessage"
    kb = calls[-1]["params"]["reply_markup"]["inline_keyboard"]
    assert kb == [[{"text": "Approve", "callback_data": "approve"},
                   {"text": "Reject", "callback_data": "reject"}]], kb
    print(f"  buttons render as inline_keyboard: {kb[0][0]} ✓")

    # with a long body the buttons ride the LAST chunk, not the first
    a, calls = _adapter()
    a.send({"channel_user_id": CHAT, "body": "line\n" * 3000,
            "buttons": [[{"text": "OK", "data": "ok"}]]})
    sends = [c for c in calls if c["method"] == "sendMessage"]
    assert len(sends) > 1, "the body should have been chunked"
    assert all("reply_markup" not in c["params"] for c in sends[:-1]), \
        "buttons must not appear on an early chunk"
    assert sends[-1]["params"]["reply_markup"], "buttons belong on the last chunk"
    print(f"  buttons ride the last of {len(sends)} chunks ✓")


def test_a_malformed_button_never_costs_the_message():
    a, calls = _adapter()
    a.send({"channel_user_id": CHAT, "body": "still delivered",
            "buttons": [[{"data": "no-label"}, "not-a-dict", {"text": "Good", "data": "g"}]]})
    params = calls[-1]["params"]
    assert params["text"] == "still delivered", "the text must still be sent"
    kb = params["reply_markup"]["inline_keyboard"]
    assert kb == [[{"text": "Good", "callback_data": "g"}]], kb
    print("  a malformed button is skipped, the message still sends ✓")


def test_answer_callback_clears_the_spinner_and_never_raises():
    a, calls = _adapter()
    assert a.answer_callback("q-1", "Approved") is True
    assert calls[-1]["method"] == "answerCallbackQuery"
    assert calls[-1]["params"] == {"callback_query_id": "q-1", "text": "Approved"}
    assert a.answer_callback(None) is False, "no query id → nothing to answer"
    a2, _ = _adapter(fail=True)
    assert a2.answer_callback("q-2") is False, "a failure must not raise"
    print("  answerCallbackQuery is sent, and failure is not fatal ✓")


def test_a_stale_topic_is_pruned_so_the_answer_still_arrives():
    """Parity: the incumbent drops a dead topic binding instead of losing the message."""
    a, calls = _adapter()
    calls_ = []

    def _api(method, params, *args, **kwargs):
        calls_.append(dict(params))
        if "message_thread_id" in params:
            return {"ok": False, "description": "Bad Request: message thread not found"}
        return {"ok": True, "result": {"message_id": 7}}

    a._api = _api
    ok = a.send({"channel_user_id": CHAT, "body": "answer", "thread_id": 99})
    assert ok is True, "the answer must still be delivered"
    assert "message_thread_id" in calls_[0], "it first tries the topic"
    assert "message_thread_id" not in calls_[-1], "then it delivers without the stale topic"
    print("  a stale topic id is pruned and the message still lands ✓")


def test_other_send_failures_are_not_silently_de_topic_ed():
    """Control: pruning must key on the topic error, not on any failure."""
    a, _ = _adapter()
    calls_ = []

    def _api(method, params, *args, **kwargs):
        calls_.append(dict(params))
        return {"ok": False, "description": "Bad Request: chat not found"}

    a._api = _api
    a.send({"channel_user_id": CHAT, "body": "x", "thread_id": 99})
    assert all("message_thread_id" in c for c in calls_), \
        "a non-topic failure must not change the routing"
    print("  a non-topic failure does not silently de-topic the chat ✓")


def test_edit_message_rewrites_a_sent_message():
    a, calls = _adapter()
    assert a.edit_message(CHAT, 5, "Approved ✓",
                          buttons=[[{"text": "Undo", "data": "undo"}]]) is True
    p = calls[-1]["params"]
    assert calls[-1]["method"] == "editMessageText"
    assert p["chat_id"] == CHAT and p["message_id"] == 5 and p["text"] == "Approved ✓"
    assert p["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "undo"
    assert a.edit_message(None, 5, "x") is False
    print("  editMessageText updates the prompt (with new buttons) ✓")


def test_a_button_press_arrives_with_its_query_id():
    a, _ = _adapter()
    env = a.parse({"update_id": 9, "callback_query": {
        "id": "q-9", "from": {"id": CHAT}, "data": "approve",
        "message": {"message_id": 17, "chat": {"id": CHAT}, "date": 1}}})
    assert env["tg_kind"] == "callback"
    assert env["tg_query_id"] == "q-9", "the query id is what clears the spinner"
    assert env["tg_msg_id"] == 17, "the message id is what an edit would rewrite"
    assert env["body"] == "[callback: approve]"
    print("  a button press carries tg_query_id + tg_msg_id ✓")


class _Tr:
    channel = "telegram"

    def __init__(self):
        self.offset = 0
        self.answered = []
        self.sent = []

    def get_updates(self, timeout=30):
        return []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True

    def answer_callback(self, query_id, text=""):
        self.answered.append(query_id)
        return True


class _Be:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, envelope):
        self.dispatched.append(dict(envelope))
        return None

    def poll_replies(self, max_n=5):
        return []


def test_the_daemon_answers_a_press_before_dispatching_it():
    tr, be = _Tr(), _Be()
    gw = D.Gateway(transport=tr, backends={"hermes": be}, allowed_users=None)
    env = {"msg_id": "m", "ts": 1, "from_agent": "", "to_agent": "", "channel": "telegram",
           "channel_user_id": CHAT, "thread_id": None, "body": "[callback: approve]",
           "media": [], "reply_to_msg_id": 17, "ack_required": False,
           "tg_kind": "callback", "tg_query_id": "q-9"}
    gw._turn(env)
    assert tr.answered == ["q-9"], "the press must be acknowledged"
    assert be.dispatched and be.dispatched[0]["body"] == "[callback: approve]", \
        "and the agent must still receive the choice"
    print("  the daemon answers the press and forwards the choice ✓")
