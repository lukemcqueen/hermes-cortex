#!/usr/bin/env python3
"""DM pairing (parity slice 4): enrolment with the owner's consent, fail-closed.

The incumbent pairs unknown senders. The property that must not regress: **an unpaired
sender's message is NEVER dispatched to the agent** — the code exchange is all they can
trigger. Everything else here is an attack or an accident the design must survive:
rate-limiting an unknown chat (notification flood), a code that outlives its usefulness, a
code replayed twice, an approved GUEST trying to enrol someone else.
"""
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import daemon as D          # noqa: E402
from cortex_gateway import pairing as P         # noqa: E402

OWNER = 900001          # in the env allowlist
GUEST = 100001          # enrolled later
STRANGER = 500005       # never enrolled


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class Tr:
    channel = "telegram"

    def __init__(self):
        self.offset = 0
        self.sent = []

    def get_updates(self, timeout=30):
        return []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True


class Be:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, envelope):
        self.dispatched.append(dict(envelope))
        return None

    def poll_replies(self, max_n=5):
        return []


def _gw(tmp_path, clock, allowed=(str(OWNER),)):
    store = P.PairingStore(tmp_path / "paired.json", clock=clock)
    tr, be = Tr(), Be()
    gw = D.Gateway(transport=tr, backends={"hermes": be},
                   allowed_users=set(allowed), pairing=store)
    return gw, tr, be, store


def _env(body, chat):
    return {"msg_id": "m", "ts": 1, "from_agent": "", "to_agent": "hermes",
            "channel": "telegram", "channel_user_id": chat, "thread_id": None,
            "body": body, "media": [], "reply_to_msg_id": None, "ack_required": False,
            "tg_kind": "message"}


def test_a_stranger_gets_a_code_and_their_message_is_never_dispatched(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    gw._turn(_env("please help me", STRANGER))
    assert not be.dispatched, "an unpaired sender's message must NEVER reach the agent"
    code = store.pending_for(STRANGER)
    assert code and len(code) == P.CODE_LEN, code
    assert any(code in s["body"] for s in tr.sent), "the stranger is told the code"
    # the owner is told, via the home channel (no channel_user_id → transport fallback)
    assert any("Pairing request" in s["body"] and code in s["body"] for s in tr.sent), tr.sent
    print(f"  stranger → code issued, nothing dispatched ({len(tr.sent)} notices) ✓")


def test_the_same_stranger_cannot_flood_the_owner(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    for _ in range(P.MAX_PENDING_PER_SENDER + 2):
        gw._turn(_env("hi", STRANGER))
    issued = [c for c, r in store.pending.items() if r["chat_id"] == str(STRANGER)]
    assert len(issued) == P.MAX_PENDING_PER_SENDER, issued
    assert not be.dispatched
    print(f"  rate limited: {len(issued)} codes per window, not {P.MAX_PENDING_PER_SENDER + 2} ✓")


def test_owner_approves_and_the_chat_is_enrolled_persistently(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    gw._turn(_env("hi", STRANGER))
    code = store.pending_for(STRANGER)

    gw._turn(_env(f"/approve {code}", OWNER))
    assert store.is_approved(STRANGER), "the code must enrol the chat"
    assert not store.pending_for(STRANGER), "the code is single-use"

    # persisted: a fresh store (a gateway restart) still knows the approval
    assert P.PairingStore(tmp_path / "paired.json", clock=clock).is_approved(STRANGER)
    # and the newly paired chat is dispatched from now on
    gw._turn(_env("now let me in", STRANGER))
    assert be.dispatched and be.dispatched[-1]["body"] == "now let me in"
    print("  approve → enrolled, persisted, and dispatched thereafter ✓")


def test_a_guest_cannot_approve_someone_else(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    # enrol GUEST by the owner, then GUEST tries to enrol STRANGER
    gw._turn(_env("hi", GUEST)); code = store.pending_for(GUEST)
    gw._turn(_env(f"/approve {code}", OWNER))
    gw._turn(_env("hi", STRANGER)); stranger_code = store.pending_for(STRANGER)

    gw._turn(_env(f"/approve {stranger_code}", GUEST))
    assert not store.is_approved(STRANGER), "an approved guest must not be able to enrol"
    assert store.pending_for(STRANGER), "and the request stays pending for the owner"
    print("  an approved guest cannot approve anyone ✓")


def test_codes_expire_and_cannot_be_replayed(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    gw._turn(_env("hi", STRANGER)); code = store.pending_for(STRANGER)
    clock.advance(P.CODE_TTL_S + 1)
    gw._turn(_env(f"/approve {code}", OWNER))
    assert not store.is_approved(STRANGER), "an expired code must not enrol"
    print(f"  a code older than {P.CODE_TTL_S}s is refused ✓")

    gw._turn(_env("hi", STRANGER)); code2 = store.pending_for(STRANGER)
    gw._turn(_env(f"/approve {code2}", OWNER))
    gw._turn(_env(f"/approve {code2}", OWNER))
    assert store.is_approved(STRANGER)
    assert not store.pending.get(code2), "a replayed code is inert"
    print("  an approval cannot be replayed ✓")


def test_deny_drops_the_request(tmp_path):
    clock = Clock()
    gw, tr, be, store = _gw(tmp_path, clock)
    gw._turn(_env("hi", STRANGER)); code = store.pending_for(STRANGER)
    gw._turn(_env(f"/deny {code}", OWNER))
    assert not store.pending_for(STRANGER) and not store.is_approved(STRANGER)
    assert not be.dispatched
    print("  deny drops the request and enrols nobody ✓")


def test_without_pairing_the_refusal_path_is_unchanged(tmp_path):
    tr, be = Tr(), Be()
    gw = D.Gateway(transport=tr, backends={"hermes": be},
                   allowed_users={str(OWNER)}, pairing=None)
    gw._turn(_env("hi", STRANGER))
    assert not be.dispatched and not tr.sent, "no pairing → silent refusal, as before"
    print("  pairing disabled → silent fail-closed refusal (unchanged) ✓")


def test_pairing_is_on_by_default_and_can_be_switched_off():
    """Parity: the incumbent pairs by default (Luke: 'switch to pairing').

    Either way the security property is the same — an unpaired sender is never dispatched —
    so the default only decides whether a stranger is OFFERED an enrolment path.
    """
    import os
    saved = os.environ.pop("TELEGRAM_PAIRING", None)
    try:
        assert P.enabled() is True, "pairing is on by default (incumbent parity)"
        for val in ("off", "0", "false", "no"):
            os.environ["TELEGRAM_PAIRING"] = val
            assert P.enabled() is False, f"{val!r} must disable pairing"
        for val in ("on", "1", "true", "yes", ""):
            os.environ["TELEGRAM_PAIRING"] = val
            assert P.enabled() is True, f"{val!r} must leave pairing on"
    finally:
        os.environ.pop("TELEGRAM_PAIRING", None)
        if saved is not None:
            os.environ["TELEGRAM_PAIRING"] = saved
    print("  pairing is ON by default, TELEGRAM_PAIRING=off disables it ✓")
