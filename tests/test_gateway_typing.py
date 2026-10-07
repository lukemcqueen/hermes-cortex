#!/usr/bin/env python3
"""Typing indicator (parity slice 1): "typing…" while a turn runs, refreshed, never fatal.

The incumbent shows a typing action while the agent works. Two properties matter and both
are asserted here: the indicator is REFRESHED for a long turn (Telegram expires it after
~5s, so sending it once is the same as not sending it), and it can never break a turn — a
chat that forbids actions or a rate limit must cost nothing but a log line.

Run: python3 -m pytest tests/test_gateway_typing.py -q -s
"""
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import daemon as D          # noqa: E402

CHAT = 100001


class FakeTransport:
    channel = "telegram"

    def __init__(self, typing_raises=False):
        self.offset = 0
        self.token = "t"
        self.sent = []
        self.typing = []
        self.updates = []
        self.typing_raises = typing_raises

    def get_updates(self, timeout=30):
        return list(self.updates)

    def parse(self, raw):
        return dict(raw) if raw else None

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True

    def send_typing(self, chat_id, thread_id=None, action="typing"):
        if self.typing_raises:
            raise RuntimeError("Telegram refused the action")
        self.typing.append({"chat_id": chat_id, "thread_id": thread_id, "action": action})
        return True


class FakeBackend:
    # Models the ASYNC backend (hermes over the bus): dispatch only enqueues and the
    # reply arrives via poll_replies. Without the declaration the daemon treats this
    # as a synchronous backend and frees the chat inside dispatch, so the busy/refresh
    # behaviour under test here would never happen.
    async_replies = True

    def __init__(self):
        self.dispatched = []
        self.replies = []

    def dispatch(self, envelope):
        self.dispatched.append(dict(envelope))
        return None

    def poll_replies(self, max_n=5):
        out, self.replies = list(self.replies), []
        return out


def _env(body="hi", chat=CHAT, thread=None):
    return {"msg_id": "m", "ts": 1, "from_agent": "", "to_agent": "hermes",
            "channel": "telegram", "channel_user_id": chat, "thread_id": thread,
            "body": body, "media": [], "reply_to_msg_id": None, "ack_required": False,
            "tg_kind": "message"}


def _gw(typing_raises=False):
    tr, be = FakeTransport(typing_raises), FakeBackend()
    return D.Gateway(transport=tr, backends={"hermes": be}, allowed_users=None), tr, be


def test_typing_is_sent_on_dispatch_with_the_thread():
    gw, tr, be = _gw()
    gw._turn(_env("hello", thread=7))
    assert tr.typing == [{"chat_id": CHAT, "thread_id": 7, "action": "typing"}], tr.typing
    print(f"  typing sent on dispatch (thread forwarded): {tr.typing[0]} ✓")


def test_typing_is_refreshed_for_a_long_turn_and_stops_when_the_reply_lands():
    gw, tr, be = _gw()
    gw._turn(_env("long job"))
    assert len(tr.typing) == 1

    gw._refresh_typing()                      # immediately after: no duplicate
    assert len(tr.typing) == 1, "a refresh inside the window must not re-send"
    print("  a refresh inside the window is a no-op ✓")

    gw.inflight[CHAT]["typing_ts"] = time.time() - gw.TYPING_REFRESH_S - 1
    gw._refresh_typing()                      # window elapsed: refresh
    assert len(tr.typing) == 2, "a turn longer than ~5s must refresh the indicator"
    print(f"  refreshed after {gw.TYPING_REFRESH_S}s (Telegram expires it ~5s) ✓")

    be.replies = [_env("done")]
    gw.drain_outbound()
    gw._refresh_typing()
    assert len(tr.typing) == 2, "no typing after the chat is free"
    print("  typing stops once the reply drains ✓")


def test_a_failing_indicator_never_breaks_the_turn():
    gw, tr, be = _gw(typing_raises=True)
    gw._turn(_env("still must run"))
    assert be.dispatched and be.dispatched[0]["body"] == "still must run", \
        "the turn must run even when the indicator fails"
    print("  a refused indicator costs a log line, not the turn ✓")


def test_a_transport_without_typing_is_still_conformant():
    class Bare(FakeTransport):
        send_typing = None                    # feature-detect must skip it, not crash

    tr, be = Bare(), FakeBackend()
    gw = D.Gateway(transport=tr, backends={"hermes": be}, allowed_users=None)
    gw._turn(_env("no typing capability"))
    assert be.dispatched, "the turn must run without the optional capability"
    print("  a transport without send_typing still works (feature-detected) ✓")


def test_typing_after_the_chat_is_free_is_a_no_op_never_an_error():
    """The keeper thread races the poll loop; the refresh path must not raise.

    `_refresh_typing` runs on the keeper thread while the poll loop may be finishing
    and popping the chat — an `in`-check followed by item assignment is a KeyError
    window across the two threads.
    """
    gw, tr, be = _gw()
    gw._typing(CHAT)                       # nothing in flight: must not raise
    assert gw.inflight == {}
    gw.inflight[CHAT] = {"ts": 0.0, "envelope": _env("x", thread=None)}
    gw._typing(CHAT)
    assert "typing_ts" in gw.inflight[CHAT], "a live turn must have its stamp updated"
    print("  typing with no in-flight turn is a no-op, not a KeyError ✓")


def test_the_typing_keeper_refreshes_while_the_loop_is_blocked_in_a_turn():
    """The refresh lives BETWEEN poll cycles, so a blocking turn froze the indicator.

    `_refresh_typing()` is called once per poll cycle, and a synchronous backend (a CLI
    agent like pi) blocks inside dispatch for the whole turn — which is measured in
    minutes, while Telegram expires a chat action after ~5s. So a long pi turn showed
    NO typing prompt at all, while the async hermes backend kept it. The keeper thread
    is what makes the prompt survive a blocked loop.
    """
    gw, tr, be = _gw()
    gw._turn(_env("long job"))
    assert len(tr.typing) == 1
    gw.inflight[CHAT]["typing_ts"] = time.time() - gw.TYPING_REFRESH_S - 1   # due now

    keeper = D._TypingKeeper(gw, interval_s=0.05)
    keeper.start()
    try:
        deadline = time.time() + 3.0
        while len(tr.typing) < 2 and time.time() < deadline:
            time.sleep(0.02)
    finally:
        keeper.stop()
    assert len(tr.typing) >= 2, "the keeper never refreshed the indicator"
    assert tr.typing[-1]["chat_id"] == CHAT, tr.typing[-1]
    print("  the keeper refreshes typing while the poll loop is blocked ✓")

    settled = len(tr.typing)
    time.sleep(0.25)
    assert len(tr.typing) == settled, "a stopped keeper must stop refreshing"
    print("  a stopped keeper stops refreshing ✓")


def test_the_keeper_reports_but_never_breaks_on_a_refresh_failure():
    """UX only: a failing chat action must not kill the keeper (or the gateway)."""
    gw, tr, be = _gw(typing_raises=True)
    gw._turn(_env("long job"))
    gw.inflight[CHAT]["typing_ts"] = time.time() - gw.TYPING_REFRESH_S - 1

    keeper = D._TypingKeeper(gw, interval_s=0.05)
    keeper.start()
    try:
        deadline = time.time() + 2.0
        while keeper.is_alive() and time.time() < deadline:
            time.sleep(0.02)
        assert keeper.is_alive(), "a refused typing action must not kill the keeper"
    finally:
        keeper.stop()
    print("  a refused action is logged, never fatal ✓")
