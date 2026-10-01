#!/usr/bin/env python3
"""CR9 — cortex-gateway uses the SAME Telegram env vars Hermes uses.

TELEGRAM_BOT_TOKEN (the bot), TELEGRAM_ALLOWED_USERS (sender allowlist),
TELEGRAM_HOME_CHANNEL (default delivery target) — no invented names. The
allowlist and home channel are required and fail closed: an open bot (no
allowlist) is exactly the fail-open class we refuse elsewhere.
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import cortex_gateway.daemon as DAEMON  # noqa: E402
import cortex_gateway.transport as TR  # noqa: E402

EXAMPLE = _REPO / "ops" / "scripts" / "gateway.yaml.example"
ALLOWED = "1001"
HOME = "1001"


# ── fakes ──────────────────────────────────────────────────────────────────
class _T:
    def __init__(self, updates):
        self._updates = updates
        self.offset = 0
        self.sent = []

    def get_updates(self, timeout=30):
        return self._updates

    def parse(self, raw):
        return raw.get("env")

    def send(self, env):
        self.sent.append(env)
        return True


class _B:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, env):
        self.dispatched.append(env)
        return None

    def poll_replies(self):
        return []


def _gw(allowed, sender):
    t = _T([{"update_id": 1, "env": {"channel_user_id": sender, "body": "hi"}}])
    b = _B()
    gw = DAEMON.Gateway(transport=t, backends={"hermes": b},
                        allowed_users=allowed)
    return gw, b


# ── allowlist enforcement ──────────────────────────────────────────────────
def test_parse_allowed_users_comma_and_space():
    assert DAEMON._parse_allowed_users("1,2 3") == {"1", "2", "3"}
    assert DAEMON._parse_allowed_users("") == set()


def test_allowed_sender_dispatches():
    gw, b = _gw({str(ALLOWED)}, ALLOWED)
    gw.poll_once()
    assert len(b.dispatched) == 1


def test_disallowed_sender_is_dropped():
    gw, b = _gw({str(ALLOWED)}, 9999)
    gw.poll_once()
    assert b.dispatched == [], "sender outside the allowlist must not dispatch"


# ── home channel ───────────────────────────────────────────────────────────
def test_send_falls_back_to_home_channel():
    a = TR.TelegramAdapter(token="t", home_channel=HOME)
    captured = {}

    def fake_api(method, params):
        captured.update(params)
        return {"ok": True}

    a._api = fake_api
    assert a.send({"body": "proactive"}) is True      # no channel_user_id
    assert str(captured["chat_id"]) == HOME


def test_send_raises_without_chat_or_home_channel():
    a = TR.TelegramAdapter(token="t")                 # no home_channel
    with pytest.raises(ValueError):
        a.send({"body": "nowhere to go"})


# ── build_gateway: same 3 vars, all required ───────────────────────────────
def _base_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("GATEWAY_SECRET", "real-secret")


def test_build_gateway_requires_allowed_users(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", HOME)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USERS", raising=False)
    with pytest.raises(SystemExit):
        DAEMON.build_gateway(EXAMPLE)


def test_build_gateway_requires_home_channel(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", ALLOWED)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    with pytest.raises(SystemExit):
        DAEMON.build_gateway(EXAMPLE)


def test_build_gateway_wires_allowed_users_and_home(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", ALLOWED)
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", HOME)
    gw = DAEMON.build_gateway(EXAMPLE)
    assert gw.allowed_users == {str(ALLOWED)}
    assert str(gw.transport.home_channel) == HOME
