#!/usr/bin/env python3
"""Slash-command parity for a `kind: command` backend — /model, /compact, /restart.

WHY THESE THREE AND NOT ONLY /new. `/new` already had a gateway-level handler
(tests/test_gateway_new_session.py). These are the commands a human reaches for
next, and like `/new` they CANNOT be forwarded to a CLI agent: pi handles its
built-in slash commands only in the interactive/RPC surfaces, so `/model x`,
`/compact` and `/restart` sent as prompt text become conversation, not commands —
`/new` used to be answered by pi as the prose "New task. What are we doing?"
while keeping every bit of context.

Each test drives the REAL gateway and the REAL CommandBackend; the agent's command
is `/bin/echo`, so the reply body IS the argv the backend built. Nothing here
re-implements the backend's logic — a fake would be the second implementation
this layer exists to remove.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import cortex_gateway.agents as AGENTS      # noqa: E402
import cortex_gateway.daemon as DAEMON      # noqa: E402
import cortex_gateway.models as MODELS      # noqa: E402
import cortex_gateway.restarts as RESTARTS  # noqa: E402
import cortex_gateway.sessions as SESSIONS  # noqa: E402

CHAT = 12345
DEFAULT_MODEL = "openrouter/moonshotai/kimi-k2.6"
PI_CONTROL = _REPO / "ops" / "scripts" / "cortex_gateway" / "pi_control.py"


class FakeTransport:
    """Just enough transport for a turn: parse an envelope, record the replies."""

    def __init__(self):
        self.sent = []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(envelope)
        return True

    def bodies(self):
        return [str(e.get("body", "")) for e in self.sent]

    def last(self) -> str:
        return self.bodies()[-1] if self.sent else ""


def _spec(**over) -> AGENTS.AgentSpec:
    """The live pi shape: a model flag declared once, per-chat sessions."""
    d = {
        "name": "pi", "kind": "command", "command": ["/bin/echo"],
        "model": DEFAULT_MODEL, "model_args": ["--model", "{model}"],
        "session": "per_chat", "session_args": ["--session-id", "{session_id}"],
        "reply_mode": "sync", "output": "raw",
    }
    d.update(over)
    return AGENTS.AgentSpec.from_dict(d)


def _gateway(tmp_path, spec=None, **over):
    spec = spec or _spec(**over)
    backend = AGENTS.CommandBackend(spec)
    transport = FakeTransport()
    gw = DAEMON.Gateway(
        transport=transport, backends={"pi": backend}, default_agent="pi",
        allowed_users=None,
        sessions=SESSIONS.SessionBook(tmp_path / "sessions.json"),
        models=MODELS.ModelBook(tmp_path / "models.json"),
        restarts=RESTARTS.RestartBook(tmp_path / "restarts.json"),
    )
    return gw, transport, backend


def _turn(gw, body, chat=CHAT):
    """A plain message. The envelope is COMPLETE (msg_id/channel/…): the real
    transport builds one, and the backend validates it — a partial dict would be
    DLQ'd and the test would silently assert on nothing."""
    gw._turn(_envelope(body, chat))


def _tell(gw, body, chat=CHAT):
    """A command turn: it is HANDLED by the gateway, never dispatched to the agent."""
    gw._turn(_envelope(body, chat))


def _envelope(body: str, chat=CHAT) -> dict:
    import uuid
    return {
        "msg_id": str(uuid.uuid4()), "ts": 1, "to_agent": "pi",
        "channel": "telegram", "channel_user_id": chat, "thread_id": None,
        "body": body, "media": [], "reply_to_msg_id": None, "ack_required": False,
        "tg_kind": "message",
    }


# ── /model ───────────────────────────────────────────────────────────────────

def test_model_switch_is_stored_persisted_and_used_on_the_next_turn(tmp_path):
    """The three halves of a working switch: stored, persisted, and ACTUALLY used.

    A switch that only replies is the silent no-op this replaces — the argv the
    backend builds is the only proof the next turn runs the new model.
    """
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/model openrouter/anthropic/claude-sonnet-4.5")
    assert "claude-sonnet-4.5" in transport.last()

    # persisted: a NEW book (a restart) still knows the chat's model
    assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == \
        "openrouter/anthropic/claude-sonnet-4.5"

    # and it reaches the argv of the next turn (echo prints the argv it was given)
    _turn(gw, "hello")
    assert "--model openrouter/anthropic/claude-sonnet-4.5" in transport.last()


def test_a_chat_with_no_switch_still_runs_the_configured_default(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _turn(gw, "hello")
    assert f"--model {DEFAULT_MODEL}" in transport.last()


def test_model_with_no_argument_reports_this_chats_model_and_the_default(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/model")
    assert DEFAULT_MODEL in transport.last()
    _tell(gw, "/model openrouter/x/y")
    _tell(gw, "/model")
    assert "openrouter/x/y" in transport.last()
    assert DEFAULT_MODEL in transport.last()      # the default is still named


def test_model_reset_returns_the_chat_to_the_default(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/model openrouter/x/y")
    _tell(gw, "/model reset")
    assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == ""
    _turn(gw, "hello")
    assert f"--model {DEFAULT_MODEL}" in transport.last()


def test_model_is_rejected_when_the_backend_says_it_does_not_exist(tmp_path):
    """`/bin/false` = the agent's own check said "no". Nothing may be stored."""
    gw, transport, _ = _gateway(tmp_path, commands={"check_model": ["/bin/false"]})
    _tell(gw, "/model no/such-model")
    assert "not a model" in transport.last()
    assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == ""


def test_model_is_accepted_with_a_note_when_the_check_could_not_run(tmp_path):
    """rc=3 is a THIRD outcome: not a pass, not a refusal — say so, do not guess."""
    gw, transport, _ = _gateway(
        tmp_path, commands={"check_model": ["/nonexistent/pi-control", "check-model"]})
    _tell(gw, "/model openrouter/x/y")
    assert "could not verify" in transport.last()
    assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == "openrouter/x/y"


def test_model_does_not_leak_across_chats(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/model openrouter/x/y", chat=111)
    _turn(gw, "hello", chat=222)
    assert "--model openrouter/x/y" not in transport.last()
    assert f"--model {DEFAULT_MODEL}" in transport.last()


def test_model_command_says_so_when_switching_is_not_configured(tmp_path):
    """models=None (a gateway.yaml-only deployment) must answer, not crash."""
    backend = AGENTS.CommandBackend(_spec())
    transport = FakeTransport()
    gw = DAEMON.Gateway(transport=transport, backends={"pi": backend},
                        default_agent="pi", allowed_users=None, models=None)
    _tell(gw, "/model openrouter/x/y")
    assert "not configured" in transport.last()


# ── /compact ─────────────────────────────────────────────────────────────────

def test_compact_runs_the_declared_command_and_reports_its_output(tmp_path):
    gw, transport, _ = _gateway(
        tmp_path, commands={"compact": ["/bin/echo", "compacted", "{session_id}"]})
    _tell(gw, "/compact")
    bodies = transport.bodies()
    assert any("compacting" in b for b in bodies)          # the interim line
    assert any("compacted hc-pi-12345" in b for b in bodies)   # templated + reported


def test_compact_says_so_when_the_backend_declares_no_compact(tmp_path):
    """rc=2 is 'this backend cannot do that' — never a silent no-op."""
    gw, transport, _ = _gateway(tmp_path)                   # no commands declared
    _tell(gw, "/compact")
    assert "not supported" in transport.last()


def test_compact_reports_could_not_run_separately_from_a_refusal(tmp_path):
    gw, transport, _ = _gateway(tmp_path, commands={"compact": ["/nonexistent/pi-control"]})
    _tell(gw, "/compact")
    assert "could not run" in transport.last()


def test_compact_reports_a_refusal_from_the_agent(tmp_path):
    gw, transport, _ = _gateway(tmp_path, commands={"compact": ["/bin/false"]})
    _tell(gw, "/compact")
    assert "refused" in transport.last()


# ── /restart ─────────────────────────────────────────────────────────────────

def test_restart_refuses_when_the_gateway_is_not_supervised(tmp_path, monkeypatch):
    """Without systemd, exiting is a KILL — refuse and say why."""
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    monkeypatch.setattr(DAEMON.Gateway, "_launchd_label_for_our_pid",
                        lambda self: "")
    gw, transport, _ = _gateway(tmp_path)
    called = []
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart",
                        lambda self, code=0: called.append(code))
    _tell(gw, "/restart")
    assert "not supervised by a service manager" in transport.last()
    assert called == []                                     # nothing exited


def test_a_daemon_inside_SOMEONE_ELSES_service_is_not_supervised(tmp_path, monkeypatch):
    """INVOCATION_ID is INHERITED by every child — it alone must not be trusted.

    Measured on this host: a hand-run daemon started from an agent session sees
    INVOCATION_ID (and hence would "restart" itself into a plain exit). The unit
    env is not enough; OUR pid must be that unit's MainPID.
    """
    monkeypatch.setenv("INVOCATION_ID", "inherited-from-another-unit")
    monkeypatch.setattr(DAEMON.Gateway, "_own_unit_name",
                        lambda self: "hermes-gateway.service")

    class _Done:
        returncode = 0
        stdout = "4242\n"          # someone else's main process

    monkeypatch.setattr(DAEMON.subprocess, "run", lambda *a, **k: _Done())
    gw, transport, _ = _gateway(tmp_path)
    assert gw._supervised_by_systemd() is False
    called = []
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart",
                        lambda self, code=0: called.append(code))
    _tell(gw, "/restart")
    assert "not supervised by a service manager" in transport.last()
    assert called == []


def test_the_supervision_check_accepts_our_own_mainpid(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "real")
    monkeypatch.setattr(DAEMON.Gateway, "_own_unit_name",
                        lambda self: "cortex-gateway-esther0001.service")

    class _Done:
        returncode = 0

        def __init__(self, pid):
            self.stdout = f"{pid}\n"

    monkeypatch.setattr(DAEMON.subprocess, "run",
                        lambda *a, **k: _Done(os.getpid()))
    gw, _, _ = _gateway(tmp_path)
    assert gw._supervised_by_systemd() is True

    # …and refuses when systemctl cannot answer, or is not there at all
    class _Fail:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(DAEMON.subprocess, "run", lambda *a, **k: _Fail())
    assert gw._supervised_by_systemd() is False

    def _boom(*a, **k):
        raise OSError("systemctl not found")

    monkeypatch.setattr(DAEMON.subprocess, "run", _boom)
    assert gw._supervised_by_systemd() is False


def test_restart_replies_then_schedules_exit_under_systemd(tmp_path, monkeypatch):
    """The reply must precede the exit, and the exit IS the restart mechanism."""
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    gw, transport, _ = _gateway(tmp_path)
    called = []
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart",
                        lambda self, code=0: called.append(code))
    _tell(gw, "/restart")
    assert "estarting the gateway" in transport.last()
    deadline = 2.0
    import time as _t
    t0 = _t.time()
    while not called and _t.time() - t0 < deadline:
        _t.sleep(0.05)
    assert called == [0], "systemd restarts on ANY exit (Restart=always) -> exit 0"


def test_the_unit_name_is_read_from_our_own_cgroup(tmp_path, monkeypatch):
    """The cgroup is the only signal that says which unit WE are in."""
    gw, _, _ = _gateway(tmp_path)
    monkeypatch.setattr(DAEMON.Path, "read_text",
                        lambda self, *a, **k: "0::/user.slice/user-1000.slice/"
                                              "user@1000.service/app.slice/"
                                              "cortex-gateway-esther0001.service\n")
    assert gw._own_unit_name() == "cortex-gateway-esther0001.service"
    monkeypatch.setattr(DAEMON.Path, "read_text",
                        lambda self, *a, **k: "0::/user.slice/user-1000.slice/"
                                              "session-3.scope\n")
    assert gw._own_unit_name() == ""


# ── /restart must be OBSERVABLE afterwards (2026-10-08, Luke's report) ───────
# The restart worked (NRestarts=1) but the chat had no evidence of it, and the
# agent — whose session deliberately survived — answered "No, I didn't restart.",
# which is the only answer the human could get. These tests pin the fix.

def test_restart_reply_says_the_conversation_is_kept(tmp_path, monkeypatch):
    """'restart' reads like 'fresh start'; say what actually happens to the session."""
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart", lambda self, code=0: None)
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/restart")
    body = transport.last()
    assert "continues" in body and "/new" in body


def test_a_restart_is_announced_at_STARTUP_with_the_operators_wording(
        tmp_path, monkeypatch):
    """The new process tells the chat it is back — no prompt from the human needed.

    Luke's wording, verbatim; the restart must not require the human to speak first
    (that is what left him asking the agent, and getting "no").
    """
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart", lambda self, code=0: None)
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/restart")
    assert not any("restarted successfully" in b for b in transport.bodies())

    # …the gateway restarts; the NEW process announces before it serves anything
    restarted, transport2, _ = _gateway(tmp_path)
    assert restarted.announce_restarts() == 1
    assert transport2.last() == DAEMON.RESTART_CONFIRMATION
    assert transport2.last() == "♻ Gateway restarted successfully. Your session continues."
    # exactly once: a second startup has nothing left to say
    assert restarted.announce_restarts() == 0
    assert len(transport2.sent) == 1


def test_the_agent_is_still_told_after_the_startup_announcement(tmp_path, monkeypatch):
    """Announcing to the HUMAN must not silence the agent-side fact.

    The session survived, so an agent asked later "did you restart?" answers from
    memory and says no — unless its first prompt after the restart carries the fact.
    The marker therefore outlives the announcement and is consumed by that turn.
    """
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart", lambda self, code=0: None)
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/restart")

    gw2, transport2, _ = _gateway(tmp_path)
    gw2.announce_restarts()
    _turn(gw2, "did you restart?")
    reply = transport2.last()
    assert "[system] The GATEWAY PROCESS restarted" in reply, reply   # the echo shows the prompt
    assert "restarted successfully" not in reply, \
        "the human was already told at startup — no second footer"

    # the marker is spent: no note, no footer on later turns
    _turn(gw2, "and again")
    assert "[system]" not in transport2.last()


def test_the_confirmation_rides_the_first_reply_when_the_announcement_failed(
        tmp_path, monkeypatch):
    """A failed startup send must not lose the news — the reply path carries it."""
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart", lambda self, code=0: None)
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/restart")

    gw2, transport2, _ = _gateway(tmp_path)

    def boom(envelope):
        raise RuntimeError("telegram unreachable")

    real_send = transport2.send                   # the FakeTransport bound method
    transport2.send = boom
    assert gw2.announce_restarts() == 0          # nothing was delivered
    assert gw2.restarts.pending(CHAT), "the marker must survive a failed announcement"

    transport2.send = real_send                  # …the chat is reachable again
    _turn(gw2, "hello")
    assert DAEMON.RESTART_CONFIRMATION in transport2.last()
    assert not gw2.restarts.pending(CHAT)


def test_a_refused_restart_leaves_no_marker(tmp_path, monkeypatch):
    """Nothing restarted, so nothing may later claim it did."""
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: False)
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/restart")
    assert "not supervised by a service manager" in transport.last()
    assert RESTARTS.RestartBook(tmp_path / "restarts.json").pending(CHAT) is None
    _turn(gw, "hello")
    assert "♻️" not in transport.last()


def test_a_stale_restart_marker_is_not_reported_as_news(tmp_path):
    """A restart nobody came back to ask about must not resurface a day later."""
    book = RESTARTS.RestartBook(tmp_path / "restarts.json", ttl_s=60)
    book.mark(CHAT, ts=time.time() - 3600)
    assert book.pending(CHAT) is None
    gw, transport, _ = _gateway(tmp_path)
    gw.restarts = book
    _turn(gw, "hello")
    assert "♻️" not in transport.last()
    # …and the stale entry is gone rather than lingering
    assert RESTARTS.RestartBook(tmp_path / "restarts.json", ttl_s=60).pending(CHAT) is None


def test_the_restart_marker_survives_the_process_that_wrote_it(tmp_path):
    """It is written by the process that EXITS, so it must live on disk."""
    book = RESTARTS.RestartBook(tmp_path / "restarts.json")
    book.mark(CHAT, pid=4321)
    reread = RESTARTS.RestartBook(tmp_path / "restarts.json")
    mark = reread.pending(CHAT)
    assert mark and mark["pid"] == 4321
    mode = (tmp_path / "restarts.json").stat().st_mode
    assert not mode & 0o077, "chat ids are personal data — the book must stay 0600"


def test_restart_book_fails_open_on_a_corrupt_file(tmp_path):
    p = tmp_path / "restarts.json"
    p.write_text("{not json")
    assert RESTARTS.RestartBook(p).pending(CHAT) is None


# ── the spec contract (fail closed at build time) ────────────────────────────

def test_the_model_is_declared_exactly_once():
    """`--model` in `command` AND `model_args` = the switch silently loses."""
    with pytest.raises(ValueError, match="declared twice"):
        _spec(command=["/bin/echo", "--model", DEFAULT_MODEL]).validate()


def test_model_args_without_a_model_placeholder_is_refused():
    with pytest.raises(ValueError, match=r"\{model\}"):
        _spec(model_args=["--model"]).validate()


def test_commands_on_a_non_command_kind_are_refused():
    """Accepted-and-ignored is the failure mode this validation exists to stop."""
    spec = AGENTS.AgentSpec(name="hermes-ish", kind="hermes",
                            commands={"compact": ["/bin/echo", "x"]})
    with pytest.raises(ValueError, match="only honoured by kind 'command'"):
        spec.validate()


def test_an_empty_control_argv_is_refused():
    with pytest.raises(ValueError, match="empty argv"):
        AGENTS.AgentSpec.from_dict({"name": "pi", "kind": "command",
                                    "command": ["pi"], "commands": {"compact": []}})


def test_unknown_keys_in_a_command_entry_are_refused():
    with pytest.raises(ValueError, match="unknown key"):
        AGENTS.AgentSpec.from_dict({"name": "pi", "kind": "command", "command": ["pi"],
                                    "commands": {"compact": {"argv": ["x"], "ttl": 5}}})


def test_a_backend_with_no_model_at_all_reports_it_instead_of_running_nonsense():
    """Empty value on a --model flag is rejected by every agent: say so, visibly."""
    spec = _spec(model="")
    backend = AGENTS.CommandBackend(spec)
    out, failure = backend._run("hello", "hc-pi-1", None, "")
    assert out == "" and "no model to pass" in failure


def test_control_templates_the_session_id_from_the_envelope(tmp_path):
    backend = AGENTS.CommandBackend(_spec(
        commands={"compact": {"argv": ["/bin/echo", "{session_id}", "{agent}"],
                              "timeout_s": 5}}))
    rc, out, err = backend.control("compact", {"channel_user_id": CHAT, "body": "/compact"})
    assert (rc, err) == (0, "")
    assert out == "hc-pi-12345 pi"


def test_control_reports_an_undeclared_command_as_rc2(tmp_path):
    backend = AGENTS.CommandBackend(_spec())
    rc, out, err = backend.control("compact", {"channel_user_id": CHAT, "body": "/compact"})
    assert rc == 2 and "does not declare" in err


# ── unknown commands still belong to the agent ───────────────────────────────

def test_an_unknown_command_is_forwarded_not_swallowed(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _turn(gw, "/totally-unknown arg")
    # echo printed the argv it was given: the command reached the agent verbatim
    assert transport.last().strip().endswith("/totally-unknown arg")


# ── boundary inputs (boundary values are where the failures live) ────────────

def test_model_book_fails_open_on_a_corrupt_file(tmp_path):
    """A damaged store must not take the bot down — worst case is the default."""
    p = tmp_path / "models.json"
    p.write_text("{not json")
    assert MODELS.ModelBook(p).get(CHAT) == ""
    p.write_text(json.dumps({"models": {"12345": 7, "999": "ok", "888": "   "}}))
    book = MODELS.ModelBook(p)
    # a non-string value and a blank one are both DROPPED, not stored as a model
    assert book.get(CHAT) == "" and book.get(888) == "" and book.get(999) == "ok"
    assert book.count() == 1


def test_model_book_is_owner_only(tmp_path):
    book = MODELS.ModelBook(tmp_path / "models.json")
    book.set(CHAT, "openrouter/x/y")
    mode = (tmp_path / "models.json").stat().st_mode
    assert not mode & 0o077, "chat ids are personal data — the book must stay 0600" 


def test_model_command_accepts_odd_but_plausible_names(tmp_path):
    """Unicode, an OpenRouter preset, and a long id must not crash the handler."""
    gw, transport, _ = _gateway(tmp_path)
    for name in ("@preset/my-preset", "어떤모델", "x" * 300):
        _tell(gw, f"/model {name}")
        assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == name


def test_model_command_with_only_whitespace_reports_status(tmp_path):
    gw, transport, _ = _gateway(tmp_path)
    _tell(gw, "/model   ")
    assert "this chat:" in transport.last()
    assert MODELS.ModelBook(tmp_path / "models.json").get(CHAT) == ""


def test_control_with_an_unknown_placeholder_runs_it_verbatim(tmp_path):
    """A bad template is a CONFIG error: run it, warn, never silently drop the step."""
    backend = AGENTS.CommandBackend(_spec(
        commands={"compact": ["/bin/echo", "{bogus}", "{session_id}"]}))
    rc, out, err = backend.control("compact", {"channel_user_id": CHAT, "body": "/compact"})
    assert rc == 0
    assert out == "{bogus} hc-pi-12345"


# ── pi-control: the verdict is the OUTPUT, not the exit code ─────────────────

def _fake_pi(tmp_path: Path, stdout: str, rc: int = 0) -> Path:
    p = tmp_path / "fake-pi"
    p.write_text(f"#!/bin/sh\necho '{stdout}'\nexit {rc}\n")
    p.chmod(0o755)
    return p


def test_pi_control_treats_no_models_matching_as_a_refusal_despite_rc0(tmp_path):
    fake = _fake_pi(tmp_path, 'No models matching "zzz"', rc=0)
    done = subprocess.run([sys.executable, str(PI_CONTROL), "check-model", "zzz"],
                          capture_output=True, text=True,
                          env={**os.environ, "PI_BIN": str(fake)})
    assert done.returncode == 1, done.stdout + done.stderr


def test_pi_control_accepts_a_table_of_models(tmp_path):
    fake = _fake_pi(tmp_path, "provider model\\nopenrouter moonshotai/kimi-k2.6", rc=0)
    done = subprocess.run([sys.executable, str(PI_CONTROL), "check-model", "kimi"],
                          capture_output=True, text=True,
                          env={**os.environ, "PI_BIN": str(fake)})
    assert done.returncode == 0
    assert "moonshotai/kimi-k2.6" in done.stdout


def test_pi_control_fails_closed_when_pi_cannot_be_run(tmp_path):
    """No launcher anywhere → rc 3 (could not verify), never a verdict.

    HOME is neutered too: the fallback candidate is ~/.pi/agent/bin/pi, so a test
    that only moves PI_BIN would silently use the host's real pi — and pass.
    """
    home = tmp_path / "empty-home"
    home.mkdir()
    done = subprocess.run([sys.executable, str(PI_CONTROL), "check-model", "kimi"],
                          capture_output=True, text=True,
                          env={**os.environ, "PI_BIN": str(tmp_path / "absent"),
                               "HOME": str(home)})
    assert done.returncode == 3          # could not verify != "not a model"


def _fake_rpc_pi(tmp_path: Path, *, message_count: int, answer_compact: bool) -> Path:
    """A stand-in for pi's RPC mode, speaking its record protocol.

    `answer_compact=False` reproduces a hang: pi accepts the command and never
    writes a response. It also RECORDS ITS ARGV, so a test can assert how the
    adapter invoked it (the --no-mcp decision is load-bearing, see below).
    """
    p = tmp_path / "fake-pi"
    p.write_text(f"""#!/usr/bin/env python3
import json, sys, time
open({str(tmp_path / "argv.txt")!r}, "w").write(" ".join(sys.argv[1:]))
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        cmd = json.loads(line)
    except ValueError:
        continue
    rid = cmd.get("id")
    t = cmd.get("type")
    if t == "get_state":
        print(json.dumps({{"id": rid, "type": "response", "command": "get_state",
                           "success": True,
                           "data": {{"messageCount": {message_count}}}}}), flush=True)
    elif t == "compact":
        {"print(json.dumps({'id': rid, 'type': 'response', 'command': 'compact', 'success': True, 'data': {'tokensBefore': 1000, 'estimatedTokensAfter': 100}}), flush=True)"
         if answer_compact else "time.sleep(600)  # the hang: accepted, never answered"}
""")
    p.chmod(0o755)
    return p


def test_pi_control_does_not_hang_on_a_chat_that_has_no_session_yet(tmp_path):
    """The live defect: compact on a not-yet-existing transcript never answers.

    The adapter must ask `get_state` first and answer honestly — otherwise a human
    typing /compact in a fresh chat (or right after /new) blocks the gateway's
    turn until its own timeout.
    """
    fake = _fake_rpc_pi(tmp_path, message_count=0, answer_compact=False)
    done = subprocess.run(
        [sys.executable, str(PI_CONTROL), "compact", "--session-id", "hc-pi-1",
         "--timeout-s", "5"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PI_BIN": str(fake)})
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no conversation yet" in done.stderr
    assert "did not answer" not in done.stderr, \
        "the adapter asked for compaction blind — the exact hang it must avoid"


def test_pi_control_compacts_when_the_session_has_messages(tmp_path):
    fake = _fake_rpc_pi(tmp_path, message_count=7, answer_compact=True)
    done = subprocess.run(
        [sys.executable, str(PI_CONTROL), "compact", "--session-id", "hc-pi-1",
         "--timeout-s", "10"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PI_BIN": str(fake)})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1,000" in done.stdout and "100" in done.stdout


def test_pi_control_runs_its_rpc_calls_without_mcp(tmp_path):
    """--no-mcp is LOAD-BEARING, not an optimisation.

    Measured 2026-10-08: with MCP enabled, pi's RPC startup sat alive and silent for
    the full deadline on ~40% of /compact calls; with `--no-mcp` it answered 8/8 in
    ~1.2s. A control call uses no MCP tool, so the servers are pure risk here.
    """
    fake = _fake_rpc_pi(tmp_path, message_count=7, answer_compact=True)
    subprocess.run(
        [sys.executable, str(PI_CONTROL), "compact", "--session-id", "hc-pi-1",
         "--timeout-s", "10"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PI_BIN": str(fake)})
    argv = (tmp_path / "argv.txt").read_text()
    assert "--no-mcp" in argv, f"the control call ran with MCP enabled: {argv}"


# ── /restart on macOS: launchd supervision + a plist that ACTUALLY relaunches ─
# Titus's report (2026-10-12, non-orchestrator macOS host): the daemon answered
# "not running under systemd" while it WAS supervised — by launchd. Two separate
# defects, and the second is the dangerous half: even once launchd is detected, a
# deliberate exit only comes back if the job's plist asks launchd to relaunch on
# that exit. launchd.plist(5) defines exactly five KeepAlive conditions
# (SuccessfulExit, NetworkState, PathState, OtherJobEnabled, Crashed) and
# `SuccessfulExit=false` means "restarted in the INVERSE condition" — a NON-zero
# exit. The shipped template carried `CrashedOrAbnormalExit`, a key in no man page,
# so launchd was given no reason to restart the gateway at all.

def _launchctl_stub(tmp_path: Path, label: str, pid_expr: str) -> Path:
    """A stand-in `launchctl list`: the job table, with a settable PID column.

    `pid_expr` is a Python expression evaluated INSIDE the stub, so "os.getppid()"
    means "the process that called me" — our own pid, without a test needing to
    know it. Any other value stands for somebody else's job.
    """
    p = tmp_path / "launchctl"
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "print('PID', 'Status', 'Label', sep='\\t')\n"
        f"print({pid_expr}, '0', {label!r}, sep='\\t')\n"
        "print('-', '0', 'com.example.other', sep='\\t')\n")
    p.chmod(0o755)
    return p


def _plist_home(tmp_path: Path, label: str, keepalive_xml: str) -> Path:
    """A HOME whose LaunchAgents holds `label` with the given KeepAlive block."""
    home = Path(tmp_path) / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / f"{label}.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<plist version="1.0"><dict>\n'
        f'  <key>Label</key><string>{label}</string>\n'
        f'  <key>KeepAlive</key>{keepalive_xml}\n'
        '</dict></plist>\n')
    return home


def _launchd_env(tmp_path, monkeypatch, *, pid_expr="os.getppid()",
                 keepalive_xml="<dict><key>SuccessfulExit</key><false/></dict>"):
    """Wire the stub `launchctl` + a matching plist, and return the job label."""
    label = "com.steadfaste.gateway"
    _launchctl_stub(tmp_path, label, pid_expr)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(_plist_home(tmp_path, label, keepalive_xml)))
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: False)
    return label


def test_launchd_supervision_comes_from_the_job_table_not_the_environment(
        tmp_path, monkeypatch):
    """Our OWN pid in launchd's job table is the proof; the env var is not.

    XPC_SERVICE_NAME is inherited by every child (as INVOCATION_ID is under
    systemd), so a hand-run daemon inside someone else's job would believe a
    restart was survivable. The PID column cannot be inherited.
    """
    _launchd_env(tmp_path, monkeypatch)
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.steadfaste.gateway")
    gw, _, _ = _gateway(tmp_path)
    assert gw._launchd_label_for_our_pid() == "com.steadfaste.gateway"
    assert gw._supervised_by_launchd() is True

    # the same label, but the running pid is NOT ours (we are a child, or a
    # different process entirely) — the inherited env var must not save it
    _launchctl_stub(tmp_path, "com.steadfaste.gateway", "os.getppid() + 1")
    assert gw._launchd_label_for_our_pid() == ""
    assert gw._supervised_by_launchd() is False


def test_no_launchctl_on_the_host_is_not_supervision(tmp_path, monkeypatch):
    """Linux has no launchctl: the probe must fail closed, not raise."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    gw, _, _ = _gateway(tmp_path)
    assert gw._launchd_label_for_our_pid() == ""
    assert gw._supervised_by_launchd() is False


def test_the_plist_keepalive_decides_which_exit_launchd_relaunches(
        tmp_path, monkeypatch):
    """Only the conditions launchd DEFINES can be relied on — and they differ.

    SuccessfulExit=false → relaunch on a non-zero exit (we exit 75).
    KeepAlive=true / SuccessfulExit=true → a clean exit is the one that returns.
    Anything else, including an invented key, gives launchd no reason at all.
    """
    label = "com.steadfaste.gateway"
    cases = [
        ("<dict><key>SuccessfulExit</key><false/></dict>",
         DAEMON.LAUNCHD_RELAUNCH_EXIT_CODE),
        ("<true/>", 0),
        ("<dict><key>SuccessfulExit</key><true/></dict>", 0),
        ("<dict><key>CrashedOrAbnormalExit</key><true/></dict>", None),
        ("<dict/>", None),
    ]
    for i, (xml, want) in enumerate(cases):
        monkeypatch.setenv("HOME", str(_plist_home(tmp_path / f"h{i}", label, xml)))
        gw, _, _ = _gateway(tmp_path)
        assert gw._launchd_keepalive_exit_code(label) == want, xml

    # a plist we cannot find is the same as one that will not relaunch
    monkeypatch.setenv("HOME", str(tmp_path / "nothing-here"))
    gw, _, _ = _gateway(tmp_path)
    assert gw._launchd_keepalive_exit_code(label) is None


def test_a_damaged_or_unreadable_plist_never_claims_a_restart(tmp_path, monkeypatch):
    """Boundary: unparseable / non-dict / KeepAlive-false must all mean "no".

    A wrong answer here exits the bot into silence, so every unverifiable shape
    takes the safe direction (None), not a guess.
    """
    label = "com.steadfaste.gateway"
    home = _plist_home(tmp_path, label, "<true/>")
    target = home / "Library" / "LaunchAgents" / f"{label}.plist"
    monkeypatch.setenv("HOME", str(home))
    gw, _, _ = _gateway(tmp_path)

    target.write_text("{not a plist at all")           # unparseable
    assert gw._launchd_keepalive_exit_code(label) is None

    target.write_bytes(b"\x00\x01\x02")                # not even text
    assert gw._launchd_keepalive_exit_code(label) is None

    _plist_home(tmp_path, label, "<false/>")           # parsed, but no reason
    assert gw._launchd_keepalive_exit_code(label) is None

    _plist_home(tmp_path, label, "<array><string>x</string></array>")
    assert gw._launchd_keepalive_exit_code(label) is None

    (home / "Library" / "LaunchAgents").mkdir(exist_ok=True)
    if target.is_file():
        target.unlink()
    target.mkdir()                                     # a directory, not a file
    assert gw._launchd_keepalive_exit_code(label) is None


def test_the_restart_exit_code_is_derived_from_the_supervisor(tmp_path, monkeypatch):
    gw, _, _ = _gateway(tmp_path)
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: True)
    assert gw._restart_exit_code() == 0                    # Restart=always
    monkeypatch.setattr(DAEMON.Gateway, "_supervised_by_systemd", lambda self: False)
    monkeypatch.setattr(DAEMON.Gateway, "_launchd_label_for_our_pid",
                        lambda self: "com.steadfaste.gateway")
    monkeypatch.setattr(DAEMON.Gateway, "_launchd_keepalive_exit_code",
                        lambda self, label: DAEMON.LAUNCHD_RELAUNCH_EXIT_CODE)
    assert gw._restart_exit_code() == DAEMON.LAUNCHD_RELAUNCH_EXIT_CODE
    monkeypatch.setattr(DAEMON.Gateway, "_launchd_label_for_our_pid", lambda self: "")
    assert gw._restart_exit_code() is None                 # no supervisor → do not exit


def test_restart_under_launchd_exits_with_the_code_launchd_relaunches(
        tmp_path, monkeypatch):
    """The whole macOS path: detected, policy honoured, reply first, then exit 75."""
    _launchd_env(tmp_path, monkeypatch)
    gw, transport, _ = _gateway(tmp_path)
    assert gw._supervised_by_launchd() is True
    called = []
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart",
                        lambda self, code=0: called.append(code))
    _tell(gw, "/restart")
    assert "estarting the gateway" in transport.last()
    deadline = 2.0
    t0 = time.time()
    while not called and time.time() - t0 < deadline:
        time.sleep(0.05)
    assert called == [DAEMON.LAUNCHD_RELAUNCH_EXIT_CODE], called


def test_restart_refuses_when_launchd_would_not_start_it_again(tmp_path, monkeypatch):
    """A job with no recognised relaunch condition: refuse and name the plist fix."""
    label = _launchd_env(tmp_path, monkeypatch,
                         keepalive_xml="<dict><key>CrashedOrAbnormalExit</key><true/></dict>")
    gw, transport, _ = _gateway(tmp_path)
    called = []
    monkeypatch.setattr(DAEMON.Gateway, "_exit_for_restart",
                        lambda self, code=0: called.append(code))
    _tell(gw, "/restart")
    body = transport.last()
    assert called == [], "exiting here is a kill — launchd has no reason to restart"
    assert label in body and "KeepAlive" in body, body
    assert RESTARTS.RestartBook(tmp_path / "restarts.json").pending(CHAT) is None


def test_the_shipped_plist_template_gives_launchd_a_reason_to_relaunch():
    """Guard for root cause 2 — the template must use conditions launchd defines.

    A KeepAlive dict of keys launchd does not know leaves it with no reason to
    restart the job, so a crash — and every /restart — parks the gateway. The five
    real conditions come from launchd.plist(5).
    """
    import plistlib
    path = _REPO / "docs" / "templates" / "com.hermes.cortex-gateway.plist"
    cfg = plistlib.loads(path.read_bytes())
    assert cfg["Label"] == "com.hermes.cortex-gateway"
    ka = cfg["KeepAlive"]
    assert isinstance(ka, dict), ka
    assert ka.get("SuccessfulExit") is False, \
        "SuccessfulExit=false is the condition the daemon's exit 75 comes back on"
    known = {"SuccessfulExit", "NetworkState", "PathState", "OtherJobEnabled", "Crashed"}
    assert set(ka) <= known, f"not launchd conditions: {sorted(set(ka) - known)}"
