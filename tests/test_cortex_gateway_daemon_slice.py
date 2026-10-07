#!/usr/bin/env python3
"""Daemon parity slice 2 — G5 (slash dispatch), G6 (busy/interrupt), G7 (poll recovery).

Each gap in docs/design/cortex-gateway-parity.md is asserted here as the daemon's actual
behaviour against fakes (no network): a fake transport, a fake backend, scripted polls and
replies. The gaps were previously registered as OPEN, asserted as today's behaviour so
that implementing them FAILED a test; these tests are that flip.

Run: python3 -m pytest tests/test_cortex_gateway_daemon_slice.py -q -s
"""
import sys
import urllib.error
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import daemon as D          # noqa: E402
from cortex_gateway import transport as T       # noqa: E402

CHAT = 100001


class FakeTransport:
    channel = "telegram"

    def __init__(self):
        self.offset = 0
        self.token = "t"
        self.home_channel = None
        self.sent = []
        self.envelope = None      # what parse() returns
        self.updates = []         # what get_updates() returns
        self.error: BaseException | None = None   # what get_updates() raises

    def get_updates(self, timeout=30):
        if self.error is not None:
            raise self.error
        return list(self.updates)

    def parse(self, raw):
        return dict(self.envelope) if self.envelope else None

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True


class FakeBackend:
    # Models the ASYNC backend (hermes over the bus): dispatch only enqueues and the
    # reply arrives via poll_replies, so the chat must stay busy until it drains.
    # A backend that answers in dispatch() (a CLI agent) leaves this False.
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


def _gw():
    tr, be = FakeTransport(), FakeBackend()
    gw = D.Gateway(transport=tr, backends={"hermes": be}, allowed_users=None)
    return gw, tr, be


def _env(body, kind="message", chat=CHAT):
    return {"msg_id": "m", "ts": 1, "from_agent": "", "to_agent": "", "channel": "telegram",
            "channel_user_id": chat, "thread_id": None, "body": body, "media": [],
            "reply_to_msg_id": None, "ack_required": False, "tg_kind": kind}


def _drive(gw, tr, body, kind="message"):
    """One inbound update through the real _turn path (parse → route → handle)."""
    tr.envelope = _env(body, kind=kind)
    gw._turn({"update_id": 1})


def _bodies(backend):
    return [e.get("body") for e in backend.dispatched]


# ── G6: busy / interrupt ─────────────────────────────────────────────

def test_one_turn_in_flight_per_chat_and_the_rest_queue():
    gw, tr, be = _gw()
    _drive(gw, tr, "first")
    _drive(gw, tr, "second")
    _drive(gw, tr, "third")
    assert _bodies(be) == ["first"], "only ONE turn may be in flight per chat"
    assert len(gw.queues[CHAT]) == 2, "arrivals must queue behind the in-flight turn"
    print(f"  G6 serialization: dispatched={_bodies(be)} queued={len(gw.queues[CHAT])}")

    # a reply frees the chat → the next queued turn starts
    be.replies = [_env("answer")]
    gw.drain_outbound()
    assert [s["body"] for s in tr.sent] == ["answer"], "the reply must be delivered"
    assert _bodies(be) == ["first", "second"], "the queue must advance after a reply"
    print(f"  G6 queue advance: dispatched={_bodies(be)} queued={len(gw.queues[CHAT])}")


def test_queue_is_bounded():
    gw, tr, be = _gw()
    gw.max_queue = 2
    for body in ("a", "b", "c", "d"):
        _drive(gw, tr, body)
    assert len(gw.queues[CHAT]) == 2, "the queue must stay bounded (oldest dropped)"
    assert [q["body"] for q in gw.queues[CHAT]] == ["c", "d"], "newest survive"
    print(f"  G6 bounded queue: kept={[q['body'] for q in gw.queues[CHAT]]} max={gw.max_queue}")


def test_slash_stop_interrupts_forwarding_and_suppresses_the_pending_reply():
    gw, tr, be = _gw()
    _drive(gw, tr, "long job")
    _drive(gw, tr, "queued behind it")
    assert len(gw.queues[CHAT]) == 1

    _drive(gw, tr, "/stop")
    # 1. the gateway forwards /stop so the AGENT can stop its own work
    assert be.dispatched[-1]["body"] == "/stop" and be.dispatched[-1]["tg_kind"] == "command"
    # 2. the queue is cleared and the chat is suppressed
    assert gw.queues.get(CHAT) in (None, []) and CHAT in gw.suppressed
    # 3. the user gets confirmation
    assert any("/stop" in s["body"] for s in tr.sent), tr.sent
    print(f"  G5/G6 /stop: forwarded={be.dispatched[-1]['tg_kind']} "
          f"queue_cleared=True ack={tr.sent[-1]['body'][:40]!r}")

    # 4. the in-flight turn's late reply is DROPPED, not delivered
    be.replies = [_env("too late")]
    gw.drain_outbound()
    assert "too late" not in [s["body"] for s in tr.sent], \
        "a reply for an interrupted turn must never be delivered"
    print("  G6 interrupted reply suppressed ✓")

    # 5. the next real message lifts the suppression
    _drive(gw, tr, "new question")
    assert CHAT not in gw.suppressed and _bodies(be)[-1] == "new question"


# ── G5: slash dispatch ───────────────────────────────────────────────

def test_status_is_answered_locally_and_not_dispatched():
    gw, tr, be = _gw()
    _drive(gw, tr, "/status")
    assert not be.dispatched, "/status must not be forwarded to the agent"
    line = tr.sent[-1]["body"]
    assert line.startswith("gateway ok") and "in flight" in line and "queued" in line
    print(f"  G5 /status answered locally: {line}")


def test_unknown_command_is_forwarded_as_a_command_not_prompt_prose():
    gw, tr, be = _gw()
    _drive(gw, tr, "/model gpt-5")
    assert be.dispatched[-1]["body"] == "/model gpt-5"
    assert be.dispatched[-1]["tg_kind"] == "command", \
        "an unhandled command must be marked, not passed as ordinary text"
    print(f"  G5 unknown command forwarded with tg_kind={be.dispatched[-1]['tg_kind']!r}")


def test_command_recognition_is_strict():
    gw, tr, be = _gw()
    for body, expect in (("hello /stop", None), ("/", None), ("/STOP", "/stop"),
                         ("/status@MyBot", "/status")):
        got = D.Gateway._command_of(_env(body))
        assert got == expect, f"{body!r} → {got!r}, expected {expect!r}"
    print("  G5 strict command parsing ✓ (mid-text slash is not a command)")


def test_plain_message_keeps_its_kind():
    gw, tr, be = _gw()
    _drive(gw, tr, "just talking")
    assert be.dispatched[-1]["tg_kind"] == "message"
    print("  G5 plain message unchanged ✓")


# ── G7: polling recovery ─────────────────────────────────────────────

def test_transient_poll_error_backs_off_instead_of_spinning():
    gw, tr, be = _gw()
    base = D.DEFAULT_POLL_SECONDS
    assert gw._poll_delay() == base
    tr.error = RuntimeError("network blip")
    gw.poll_once()                     # must NOT raise
    assert gw.consecutive_failures == 1
    assert gw._poll_delay() > base, "a failure must widen the poll interval"
    for _ in range(6):
        gw.poll_once()
    assert gw._poll_delay() <= 60.0, "backoff must be capped"
    print(f"  G7 backoff: 1 failure → {base * 2}s, {gw.consecutive_failures} failures "
          f"→ {gw._poll_delay():.0f}s (capped)")

    tr.error = None
    gw.poll_once()                     # success resets
    assert gw.consecutive_failures == 0 and gw._poll_delay() == base
    print("  G7 recovery resets the interval ✓")


def test_conflict_stands_by_then_exits_so_it_never_steals_updates():
    gw, tr, be = _gw()
    tr.error = T.PollingConflict("Conflict: terminated by other getUpdates request")
    gw.poll_once()
    gw.poll_once()
    assert gw.consecutive_conflicts == 2, "a transient conflict must be tolerated"
    print(f"  G7 conflict tolerated: {gw.consecutive_conflicts}/{gw.max_conflicts}")
    try:
        gw.poll_once()
        raise AssertionError("persistent conflicts must exit — a second poller owns the bot")
    except SystemExit as e:
        assert e.code == 4, e.code
    print("  G7 persistent conflict exits 4 ✓")


def test_409_http_error_is_treated_as_a_conflict():
    gw, tr, be = _gw()
    tr.error = urllib.error.HTTPError("u", 409, "Conflict", None, None)  # type: ignore[arg-type]
    gw.poll_once()
    assert gw.consecutive_conflicts == 1 and gw.consecutive_failures == 0
    print("  G7 HTTP 409 routed to the conflict path ✓")


def test_success_resets_both_counters():
    gw, tr, be = _gw()
    gw.consecutive_failures, gw.consecutive_conflicts = 3, 2
    tr.updates = []
    gw.poll_once()
    assert (gw.consecutive_failures, gw.consecutive_conflicts) == (0, 0)
    print("  G7 counters reset on a clean poll ✓")
