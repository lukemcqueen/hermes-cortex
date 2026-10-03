#!/usr/bin/env python3
"""/new on the decoupled gateway — ARCHIVE semantics.

Luke's call (2026-10-03): `/new` starts a fresh conversation while KEEPING the
previous one. These tests pin both halves of that, because either alone is a bug:

  * the session id the agent is invoked with CHANGES (otherwise nothing is fresh),
  * the previous id is reported and still resolves (otherwise history was destroyed).

Before this, `/new` was forwarded to the agent as the literal text "/new": pi
answered it as prose ("New task. What are we doing?") and kept every bit of context.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import cortex_gateway.agents as AGENTS      # noqa: E402
import cortex_gateway.daemon as DAEMON      # noqa: E402
import cortex_gateway.sessions as SESSIONS  # noqa: E402

UPDATE_SH = _REPO / "ops" / "scripts" / "cortex-update.sh"
CHAT = "12345"


class FakeTransport:
    """Just enough transport for a turn: parse an envelope, record the replies."""

    def __init__(self):
        self.sent = []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(envelope)
        return True


class FakeBackend:
    """Records dispatches. Session naming is NOT re-implemented here — the real
    CommandBackend is exercised separately below, so a naming bug cannot hide."""

    def __init__(self):
        self.dispatched = []

    def dispatch(self, envelope, sink=None):
        self.dispatched.append(envelope)
        return None


def _real_backend():
    """The REAL pi backend, built from a real spec (never spawned).

    The env block mirrors the live config exactly: it is what pins session identity.
    """
    spec = AGENTS.AgentSpec.from_dict({
        "name": "pi", "kind": "command", "command": ["/bin/true"],
        "session": "per_chat", "session_args": ["--session-id", "{session_id}"],
        "env": {"CORTEX_SESSION_HARNESS": "pi", "CORTEX_SESSION_KEY": "{session_id}"},
    })
    return AGENTS.CommandBackend(spec)


def _turn(gateway, body, chat=CHAT):
    gateway._turn({"channel_user_id": chat, "body": body, "tg_kind": "message"})


def _gateway(book, backend):
    return DAEMON.Gateway(transport=FakeTransport(), backends={"pi": backend},
                          default_agent="pi", allowed_users=None, sessions=book)


# ── the real session-id derivation ──────────────────────────────────

def test_generation_zero_keeps_the_original_session_id():
    """CONTROL: a chat that never used /new must keep EXACTLY its old id.

    This is what makes the change non-migrating: no existing conversation moves,
    and no history is stranded under an id nobody will ask for again.
    """
    backend = _real_backend()
    assert backend.session_id_for({"channel_user_id": CHAT}) == f"hc-pi-{CHAT}"
    assert backend.session_id_for({"channel_user_id": CHAT,
                                   "session_generation": 0}) == f"hc-pi-{CHAT}"


def test_a_generation_changes_the_session_id():
    backend = _real_backend()
    first = backend.session_id_for({"channel_user_id": CHAT})
    second = backend.session_id_for({"channel_user_id": CHAT, "session_generation": 1})
    third = backend.session_id_for({"channel_user_id": CHAT, "session_generation": 2})
    assert len({first, second, third}) == 3, "each generation must be a distinct session"
    assert second.endswith("-g1") and third.endswith("-g2")
    # The archived ids remain DERIVABLE, which is what makes the archive findable.
    assert first.endswith(f"hc-pi-{CHAT}")


def test_a_bool_generation_is_not_read_as_generation_one():
    """bool is an int subclass; True must not silently rotate a chat."""
    backend = _real_backend()
    assert backend.session_id_for({"channel_user_id": CHAT,
                                   "session_generation": True}) == f"hc-pi-{CHAT}"


def test_a_junk_generation_is_ignored_rather_than_crashing():
    backend = _real_backend()
    for junk in ("1", None, -1, [], {}):
        assert backend.session_id_for({"channel_user_id": CHAT,
                                       "session_generation": junk}) == f"hc-pi-{CHAT}"


def test_the_session_KEY_env_follows_the_generation():
    """The argv is only half the isolation.

    The harness resumes a checkpoint keyed by `CORTEX_SESSION_KEY`. If that key does
    NOT follow the generation, `/new` rotates the transcript while the agent silently
    resumes the same checkpoint — a new session carrying the old memory, which is the
    worst of both worlds and very hard to notice. Proven the hard way: a harness that
    hand-built its own args produced exactly that false result.
    """
    backend = _real_backend()
    inbound = {"channel_user_id": CHAT}
    before = backend._child_env(inbound, f"hc-pi-{CHAT}")
    after = backend._child_env(inbound, f"hc-pi-{CHAT}-g1")
    assert before and after, "the spec declares env, so it must be returned"
    assert before["CORTEX_SESSION_KEY"] == f"hc-pi-{CHAT}"
    assert after["CORTEX_SESSION_KEY"] == f"hc-pi-{CHAT}-g1"
    assert before["CORTEX_SESSION_KEY"] != after["CORTEX_SESSION_KEY"]


# ── the /new command itself ─────────────────────────────────────────

def test_new_is_consumed_by_the_gateway_not_sent_to_the_agent():
    """The whole point: '/new' must never reach the agent as a prompt again."""
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        backend = FakeBackend()
        gw = _gateway(book, backend)
        _turn(gw, "/new")
        assert backend.dispatched == [], (
            "/new was forwarded to the agent, which is how it came to be answered "
            "as prose")
        assert gw.transport.sent, "the gateway must confirm the rotation"
        assert "archived" in gw.transport.sent[-1]["body"].lower()


def test_new_rotates_the_generation_for_that_chat_only():
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        gw = _gateway(book, FakeBackend())
        _turn(gw, "/new", chat=CHAT)
        assert book.generation(CHAT) == 1
        assert book.generation("99999") == 0, "another chat must not be affected"


def test_genuine_messages_after_new_carry_the_new_generation():
    """The rotation has to reach the backend, not just the book."""
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        backend = FakeBackend()
        gw = _gateway(book, backend)
        _turn(gw, "/new")
        _turn(gw, "hello")
        assert backend.dispatched, "an ordinary turn must still dispatch"
        assert backend.dispatched[-1]["session_generation"] == 1


def test_two_rotations_are_monotonic_and_never_reuse_an_id():
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        gw = _gateway(book, FakeBackend())
        _turn(gw, "/new")
        _turn(gw, "/new")
        assert book.generation(CHAT) == 2


def test_the_archived_session_is_named_in_the_reply():
    """Archive is only useful if the transcript is findable afterwards."""
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        gw = _gateway(book, _real_backend())
        _turn(gw, "/new")
        body = gw.transport.sent[-1]["body"]
        assert f"hc-pi-{CHAT}" in body, (
            "the reply must name the session being archived, or nobody can find it")


def test_new_before_any_session_still_names_something_derivable():
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        gw = _gateway(book, _real_backend())
        _turn(gw, "/new")
        assert f"hc-pi-{CHAT}" in gw.transport.sent[-1]["body"]


def test_new_without_a_configured_book_says_so_and_does_not_crash():
    gw = _gateway(None, FakeBackend())
    _turn(gw, "/new")
    assert "not configured" in gw.transport.sent[-1]["body"].lower()


def test_help_advertises_new():
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        gw = _gateway(book, FakeBackend())
        _turn(gw, "/help")
        assert "/new" in gw.transport.sent[-1]["body"]


def test_new_with_a_bot_suffix_is_recognised():
    """/new@Esther0001Bot is what Telegram sends in a group."""
    with tempfile.TemporaryDirectory() as tmp:
        book = SESSIONS.SessionBook(Path(tmp) / "sessions.json")
        backend = FakeBackend()
        gw = _gateway(book, backend)
        _turn(gw, "/new@Esther0001Bot")
        assert book.generation(CHAT) == 1
        assert backend.dispatched == []


# ── the book persists (a restart must not resume the archived chat) ──

def test_the_generation_survives_a_restart():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sessions.json"
        first = SESSIONS.SessionBook(path)
        first.rotate(CHAT)
        first.rotate(CHAT)

        reopened = SESSIONS.SessionBook(path)          # a fresh gateway process
        assert reopened.generation(CHAT) == 2, (
            "an in-memory counter would resume the ARCHIVED conversation after a "
            "restart and make /new look broken")


def test_a_corrupt_book_fails_open_at_generation_zero():
    """Worst case is one chat resuming its archived session; taking the bot down to
    protect a context boundary is the worse failure."""
    for junk in ("{not json", "", json.dumps({"generations": "lots"}),
                 json.dumps({"generations": {"12345": "two"}})):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions.json"
            path.write_text(junk)
            assert SESSIONS.SessionBook(path).generation(CHAT) == 0


def test_a_bool_in_the_book_is_not_a_generation():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sessions.json"
        path.write_text(json.dumps({"generations": {CHAT: True}}))
        assert SESSIONS.SessionBook(path).generation(CHAT) == 0


def test_the_book_is_not_world_readable():
    """Chat ids are personal data."""
    import os as _os
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sessions.json"
        SESSIONS.SessionBook(path).rotate(CHAT)
        mode = _os.stat(path).st_mode & 0o777
        assert mode & 0o077 == 0, f"book mode {oct(mode)} is group/other readable"


# ── deploy ──────────────────────────────────────────────────────────

def test_sessions_module_is_registered_for_deploy():
    """A module that is imported but not registered ships as an ImportError on the
    host while the repo tests stay green."""
    src = UPDATE_SH.read_text()
    assert "cortex_gateway/sessions.py" in src, (
        "sessions.py must be in the deploy register, or the gateway cannot start")


def test_the_gateway_names_the_session_module_it_imports():
    """It imports `from . import sessions`, so the register path and the import must
    agree — a rename in one place only is the classic silent break."""
    src = (_REPO / "ops" / "scripts" / "cortex_gateway" / "daemon.py").read_text()
    assert re.search(r"from \. import sessions", src)
