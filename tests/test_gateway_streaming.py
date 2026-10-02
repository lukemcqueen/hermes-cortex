#!/usr/bin/env python3
"""Streaming (parity slice 6): show a turn's output as it is produced.

The trap this file exists to catch: naive streaming sends a NEW message per partial, so a
single answer arrives as a dozen messages and the chat is unusable. The design is ONE message
that is EDITED, and the final text must land on that same message — not as a second copy.

Streaming is a courtesy, never the delivery path: any failure (no edit support, a refused
edit) must leave the final answer delivered normally.
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import agents as A          # noqa: E402
from cortex_gateway import daemon as D          # noqa: E402


class Tr:
    channel = "telegram"

    def __init__(self, allow_text=True, edit_ok=True):
        self.offset = 0
        self.sent = []
        self.texts = []
        self.edits = []
        self.allow_text = allow_text
        self.edit_ok = edit_ok

    def get_updates(self, timeout=30):
        return []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True

    def send_text(self, chat_id, text, thread_id=None):
        if not self.allow_text:
            return None
        self.texts.append(text)
        return 70 + len(self.texts)          # a message_id

    def edit_message(self, chat_id, message_id, text, buttons=None, parse_mode=""):
        if not self.edit_ok:
            return False
        self.edits.append((message_id, text))
        return True


def _spec(**kw):
    d = {"name": "slow", "kind": "command", "command": ["sh", "-c", "printf 'one\\ntwo\\n'"]}
    d.update(kw)
    return A.AgentSpec.from_dict(d)


def _env(body="go"):
    # msg_id must be a UUID: env.validate enforces it, and a synthetic "m" is rejected
    # silently (dispatch returns None) — which is exactly what made this file fail first.
    import uuid
    return {"msg_id": str(uuid.uuid4()), "ts": 1, "from_agent": "", "to_agent": "hermes",
            "channel": "telegram", "channel_user_id": 900001, "thread_id": None,
            "body": body, "media": [], "reply_to_msg_id": None, "ack_required": False,
            "tg_kind": "message"}


class NoEditTr:
    """A transport that cannot stream at all (no send_text / edit_message)."""

    channel = "telegram"

    def __init__(self):
        self.sent = []

    def get_updates(self, timeout=30):
        return []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True


def test_streaming_edits_one_message_and_never_doubles_the_answer():
    tr = Tr()
    backend = A.CommandBackend(_spec(stream=True))
    gw = D.Gateway(transport=tr, backends={"hermes": backend}, allowed_users=None)
    gw._turn(_env())
    assert len(tr.texts) == 1, f"one live message, not one per partial: {tr.texts}"
    assert tr.edits, "the message is UPDATED as output arrives"
    assert not tr.sent, "the final answer must NOT also be sent as a second message"
    assert tr.edits[-1][1] == "one\ntwo", f"the message ends on the final text: {tr.edits[-1]}"
    print(f"  stream=true → 1 message, {len(tr.edits)} edit(s), no duplicate ✓")


def test_without_the_flag_the_turn_is_synchronous():
    tr = Tr()
    backend = A.CommandBackend(_spec(stream=False))
    gw = D.Gateway(transport=tr, backends={"hermes": backend}, allowed_users=None)
    gw._turn(_env())
    assert not tr.texts and not tr.edits, "no streaming when the spec does not ask for it"
    assert tr.sent and tr.sent[-1]["body"] == "one\ntwo", "the ordinary reply path is used"
    print("  stream=false → unchanged synchronous behaviour (control) ✓")


def test_a_transport_without_edit_support_still_delivers():
    """The courtesy must never become a dependency: no edits → normal reply."""
    tr = NoEditTr()
    backend = A.CommandBackend(_spec(stream=True))
    gw = D.Gateway(transport=tr, backends={"hermes": backend}, allowed_users=None)
    gw._turn(_env())
    assert tr.sent and "one" in tr.sent[-1]["body"], "the answer is delivered normally"
    print("  no edit support → falls back to the ordinary reply ✓")


def test_a_refused_edit_does_not_lose_the_answer():
    tr = Tr(edit_ok=False)
    backend = A.CommandBackend(_spec(stream=True))
    gw = D.Gateway(transport=tr, backends={"hermes": backend}, allowed_users=None)
    gw._turn(_env())
    assert tr.sent and tr.sent[-1]["body"] == "one\ntwo", \
        "an edit the platform refuses must still end in a delivered answer"
    print("  a refused edit still ends with a delivered answer ✓")


def test_partials_are_throttled():
    """Telegram rate-limits edits; a partial per line would be rejected and unreadable."""
    import time as _t
    tr = Tr()
    gw = D.Gateway(transport=tr, backends={}, allowed_users=None)
    st = D._Streamer(gw, 900001, {})
    st.partial("a")
    st.partial("a" + "b" * 10)          # inside the interval → skipped
    assert len(tr.texts) == 1, "only the first partial is sent"
    st.last_at = _t.time() - D._Streamer.MIN_INTERVAL_S - 1
    st.partial("a" + "c" * 20)
    assert tr.edits and len(tr.edits) == 1, "after the interval the message is updated"
    print(f"  partials throttled to one update per {D._Streamer.MIN_INTERVAL_S}s ✓")


def test_a_send_failure_disables_streaming_rather_than_repeating_it():
    tr = Tr(allow_text=False)
    backend = A.CommandBackend(_spec(stream=True))
    gw = D.Gateway(transport=tr, backends={"hermes": backend}, allowed_users=None)
    gw._turn(_env())
    assert not tr.texts, "no partials could be sent"
    assert tr.sent and tr.sent[-1]["body"] == "one\ntwo", "the answer still arrives once"
    print("  a failed stream send → answer delivered once, no retry loop ✓")


def test_stream_is_declared_in_the_registry_not_hardcoded():
    """Adding a streaming agent is config, like every other capability."""
    s = _spec(stream=True)
    assert s.stream is True
    assert _spec().stream is False, "streaming is opt-in per agent"
    try:
        A.AgentSpec.from_dict({"name": "x", "kind": "command", "command": ["true"],
                               "stream": True, "streem": True})
        raise AssertionError("a typo must be refused, not silently ignored")
    except ValueError:
        pass
    print("  stream is spec-declared and unknown keys stay rejected ✓")
