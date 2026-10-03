#!/usr/bin/env python3
"""The two guards that make a second-bot gateway safe to run on this host.

**1. `guard_distinct_token.py`** — an `ExecStartPre` that REFUSES to start a unit
whose `token_ref` resolves to the LIVE bot's token. That separation used to be a
comment at the top of the unit file. **A comment is not a guard: it cannot fail,
and it never runs.** Enabling the production unit while `hermes-gateway.service`
runs would put a second poller on the live token, Telegram answers 409, and the
casualty is the live channel.

The guard is exercised as a SUBPROCESS with a controlled environment, so these
tests prove the real thing systemd will run — not a re-implementation of it.

**2. The persisted poll offset** — the only record of which Telegram updates this
bot already consumed. Held in memory alone it resets to `initial_offset` on every
restart, and the unit restarts on any crash (`Restart=always`).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import cortex_gateway.transport as TRANSPORT  # noqa: E402

GUARD = _REPO / "ops" / "scripts" / "cortex_gateway" / "guard_distinct_token.py"
LIVE = "TELEGRAM_BOT_TOKEN"
SECOND = "ESTHER0001_BOT_TOKEN"

# Synthetic tokens — never the real ones.
LIVE_VALUE = "111111:AAAA-live-bot-token-placeholder"
SECOND_VALUE = "222222:BBBB-second-bot-token-placeholder"


def _run_guard(config_text: str, env_extra: dict) -> subprocess.CompletedProcess:
    """Run the real guard against a config written to a temp dir.

    `timeout=60` sits on the `subprocess.run(` line on purpose: the A4 scanner
    reads one line at a time, so a timeout on a continuation line reads as absent
    and the call gets flagged as unbounded.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "gateway.yaml"
        cfg.write_text(config_text)
        env = dict(os.environ)
        env.pop(LIVE, None)
        env.pop(SECOND, None)
        env.update(env_extra)
        argv = [sys.executable, str(GUARD), str(cfg)]
        return subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60)


def _config(token_ref: str) -> str:
    return json.dumps({"bots": [{"token_ref": token_ref, "channel": "telegram"}]})


# ── the token guard ─────────────────────────────────────────────────

def test_guard_refuses_when_the_config_points_at_the_live_token_var():
    """Naming the live var IS the production config, whatever it currently holds.

    Refused on the NAME as well as the value, so rotating the live token cannot
    turn a dangerous config into an accepted one.
    """
    r = _run_guard(_config(LIVE), {LIVE: LIVE_VALUE})
    assert r.returncode != 0, "the guard must refuse a config that names the live token"
    assert "REFUSING TO START" in r.stderr


def test_guard_refuses_when_the_two_values_are_identical():
    """A different var name pointing at the same token is the same hazard."""
    r = _run_guard(_config(SECOND), {LIVE: LIVE_VALUE, SECOND: LIVE_VALUE})
    assert r.returncode != 0, "equal token values must be refused"
    assert "REFUSING TO START" in r.stderr


def test_guard_never_prints_the_token_value():
    """A guard that leaks the secret to the journal is a new problem."""
    r = _run_guard(_config(SECOND), {LIVE: LIVE_VALUE, SECOND: LIVE_VALUE})
    assert LIVE_VALUE not in r.stdout and LIVE_VALUE not in r.stderr
    assert SECOND_VALUE not in r.stdout and SECOND_VALUE not in r.stderr


def test_control_guard_allows_a_genuinely_distinct_token():
    """CONTROL: a distinct token MUST start. A guard that refuses everything is not
    a guard — it is an outage."""
    r = _run_guard(_config(SECOND), {LIVE: LIVE_VALUE, SECOND: SECOND_VALUE})
    assert r.returncode == 0, f"a distinct token must be allowed; stderr={r.stderr!r}"
    assert "REFUSING" not in r.stderr


def test_guard_refuses_when_its_own_token_is_unset():
    """Fail closed on a missing token: a gateway that cannot authenticate must not
    be started half-configured."""
    r = _run_guard(_config(SECOND), {LIVE: LIVE_VALUE})
    assert r.returncode != 0
    assert "not set in the environment" in r.stderr


def test_guard_refuses_an_unreadable_or_empty_config():
    for text in ("not json at all", json.dumps({"bots": []}),
                 json.dumps({"bots": [{"channel": "telegram"}]})):
        r = _run_guard(text, {LIVE: LIVE_VALUE, SECOND: SECOND_VALUE})
        assert r.returncode != 0, f"must refuse config {text!r}"


def test_both_shipped_units_carry_the_guard_as_ExecStartPre():
    """The guard is only a guard if a unit RUNS it — a script nobody calls is the
    comment again, in a different file."""
    units = [_REPO / "docs" / "templates" / "cortex-gateway.service",
             Path.home() / ".config" / "systemd" / "user"
             / "cortex-gateway-esther0001.service"]
    for unit in units:
        if not unit.is_file():
            continue
        text = unit.read_text()
        assert "ExecStartPre=" in text, f"{unit.name} has no ExecStartPre"
        assert "guard_distinct_token.py" in text, (
            f"{unit.name} does not run the live-token guard")
        # It must come BEFORE ExecStart, or the daemon starts first.
        assert text.index("ExecStartPre=") < text.index("ExecStart="), (
            f"{unit.name}: ExecStartPre must precede ExecStart")


def test_the_guard_is_registered_for_deploy():
    """A guard that is not registered ships as an ImportError on the host while the
    repo tests stay green — the deploy syncs an explicit list."""
    src = (_REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
    assert "cortex_gateway/guard_distinct_token.py" in src, (
        "guard_distinct_token.py must be in the deploy register, or the unit's "
        "ExecStartPre points at a file the host never receives")


# ── the persisted poll offset ───────────────────────────────────────

def test_offset_is_persisted_and_reloaded_across_a_restart():
    """The core property: a restart resumes, it does not re-read."""
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state" / "gateway-offset.json"
        first = TRANSPORT.TelegramAdapter(token="t", initial_offset=0, state_path=state)
        assert first.offset == 0
        first.set_offset(4242)
        assert state.is_file(), "set_offset must write the state file"

        # A NEW adapter = a restarted process.
        second = TRANSPORT.TelegramAdapter(token="t", initial_offset=0, state_path=state)
        assert second.offset == 4242, (
            "a restart must resume at the persisted offset, not initial_offset")


def test_offset_never_moves_backwards():
    """Telegram's offset is monotonic; re-sending an update is a duplicate reply."""
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state" / "o.json"
        a = TRANSPORT.TelegramAdapter(token="t", state_path=state)
        a.set_offset(100)
        a.set_offset(50)                       # a stale/duplicated call
        assert a.offset == 100
        assert json.loads(state.read_text())["offset"] == 100


def test_initial_offset_cannot_lower_a_persisted_offset():
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state" / "o.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"offset": 900}))
        a = TRANSPORT.TelegramAdapter(token="t", initial_offset=5, state_path=state)
        assert a.offset == 900


def test_a_corrupt_offset_file_does_not_stop_the_poller():
    """A damaged state file must degrade to 'start from initial_offset', never
    crash the gateway — the bot staying up outranks the resume point."""
    for junk in ("{not json", "", json.dumps({"offset": "lots"}),
                 json.dumps({"offset": True}), json.dumps({"offset": -7})):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state" / "o.json"
            state.parent.mkdir(parents=True)
            state.write_text(junk)
            a = TRANSPORT.TelegramAdapter(token="t", initial_offset=3, state_path=state)
            assert a.offset == 3, f"junk {junk!r} must fall back to initial_offset"


def test_no_state_path_keeps_the_old_in_memory_behaviour():
    """A transport with nowhere to persist must still work (and not crash)."""
    a = TRANSPORT.TelegramAdapter(token="t", initial_offset=7)
    assert a.offset == 7
    a.set_offset(11)
    assert a.offset == 11


def test_daemon_persists_through_the_transport():
    """The daemon must call set_offset, not poke the attribute — otherwise the
    persistence exists but nothing ever uses it."""
    src = (_REPO / "ops" / "scripts" / "cortex_gateway" / "daemon.py").read_text()
    assert "set_offset" in src, "the daemon must persist the offset through the transport"
    assert 'f"gateway-offset-{bot.token_ref}.json"' in src, (
        "the state file must be keyed by token_ref, so two gateways on one host "
        "never share a resume point")
