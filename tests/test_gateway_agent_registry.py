#!/usr/bin/env python3
"""The agent registry: adding an agent is CONFIG, and a bad config fails at BUILD time.

Luke (2026-10-02): "consider making generic interfaces so we can add new coding agents
easily (with different functions)". These tests are that promise made checkable:

- a new kind is a registry line (proved by registering one here and using it),
- a new agent of an existing kind is a spec (no code),
- every bad spec fails LOUDLY at build time with a message naming the entry — because the
  alternative is a silently unwired agent that swallows human messages (exactly what the
  cutover rehearsal found with the placeholder agent name).

Run: python3 -m pytest tests/test_gateway_agent_registry.py -q -s
"""
import json
import shlex
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import gateway_envelope as env                                  # noqa: E402
from cortex_gateway import agents as A                          # noqa: E402


def _inbound(body="hello", chat=100001):
    return {"msg_id": env.new_msg_id(), "ts": int(time.time()), "from_agent": "",
            "to_agent": "pi", "channel": "telegram", "channel_user_id": chat,
            "thread_id": 42, "body": body, "media": [], "reply_to_msg_id": None,
            "ack_required": False}


# ── adding an AGENT is config ────────────────────────────────────────

def test_a_new_agent_is_a_spec_not_code():
    ctx = {"bus_url": "https://bus.example.com", "bus_headers": {}, "secret": "s" * 32}
    built = A.build_backends([
        {"name": "esther", "kind": "hermes"},
        {"name": "pi", "kind": "command",
         "command": ["/bin/echo", "pi says:"],
         "model": "openrouter/moonshotai/kimi-k2.6",
         "capabilities": ["code", "review"], "timeout_s": 60, "reply_mode": "sync"},
    ], ctx)
    assert set(built) == {"esther", "pi"}
    assert built["esther"].spec.kind == "hermes"
    assert built["pi"].spec.kind == "command"
    assert built["pi"].spec.capabilities == ["code", "review"]
    assert built["pi"].health()["ok"] is True
    print("  two agents, two kinds, ZERO gateway changes ✓")


def test_adding_a_new_KIND_is_one_registry_line():
    class _Echo:
        def __init__(self, spec, ctx):
            self.spec = spec

        def start(self): pass
        def stop(self): pass
        def dispatch(self, envelope): return None
        def poll_replies(self, max_n=5): return []
        def health(self): return {"ok": True, "backend": "echo"}

    A.register_kind("echo")(lambda spec, ctx: _Echo(spec, ctx))
    try:
        built = A.build_backends([{"name": "custom", "kind": "echo"}], {})
        assert built["custom"].health()["backend"] == "echo"
        assert "echo" in A.known_kinds()
        print(f"  a new KIND registers in one line; known kinds: {A.known_kinds()} ✓")
    finally:
        A._KINDS.pop("echo", None)


# ── bad config fails at BUILD time, naming the entry ─────────────────

def test_unknown_kind_fails_closed_and_lists_the_kinds():
    try:
        A.build_backends([{"name": "ghost", "kind": "nope"}], {})
        raise AssertionError("an unknown kind must not build")
    except ValueError as e:
        msg = str(e)
        assert "ghost" in msg and "unknown kind" in msg and "hermes" in msg, msg
        print(f"  unknown kind → {msg[:76]}… ✓")


def test_command_kind_without_a_command_is_refused():
    try:
        A.build_backends([{"name": "pi", "kind": "command"}], {})
        raise AssertionError("kind=command without a command must not build")
    except ValueError as e:
        assert "needs a 'command'" in str(e)
        print("  command kind without a command is refused at build ✓")


def test_unknown_spec_keys_are_refused():
    """A typo'd key must be an error, not silently ignored (a silently ignored
    `comand:` is an agent that never runs)."""
    try:
        A.build_backends([{"name": "pi", "kind": "command", "comand": ["pi"]}], {})
        raise AssertionError("unknown spec keys must not build")
    except ValueError as e:
        assert "unknown key" in str(e) and "comand" in str(e)
        print("  a typo'd spec key is refused ✓")


def test_duplicate_names_and_bad_reply_mode_and_subject_are_refused():
    cases = (
        ([{"name": "a"}, {"name": "a"}], "duplicate"),
        ([{"name": "a", "reply_mode": "maybe"}], "reply_mode"),
        ([{"name": "a", "subject": "user_message"}], "UPPER_CASE"),
        ([{"name": ""}], "required"),
    )
    for specs, expect in cases:
        try:
            A.build_backends(specs, {"secret": "s" * 32})
            raise AssertionError(f"{specs} must not build")
        except ValueError as e:
            assert expect in str(e), f"expected {expect!r} in {e}"
    print("  duplicates, bad reply_mode, lowercase subject and empty name all refused ✓")


def test_hermes_kind_requires_a_secret():
    try:
        A.build_backends([{"name": "esther", "kind": "hermes"}], {"secret": ""})
        raise AssertionError("kind=hermes without a secret must not build")
    except ValueError as e:
        assert "GATEWAY_SECRET" in str(e)
        print("  kind=hermes without a secret is refused (no forgeable signatures) ✓")


# ── the command backend: any CLI agent, same class ───────────────────

def test_command_backend_turns_stdout_into_a_routed_reply():
    spec = A.AgentSpec(name="pi", kind="command",
                       command=["/bin/echo", "answer:"], reply_mode="sync")
    backend = A.CommandBackend(spec)
    reply = backend.dispatch(_inbound("what is 2+2?"))
    assert reply is not None
    env.validate(reply)
    assert reply["body"] == "answer: what is 2+2?"
    # ROUTING comes from the origin: the agent does not decide where a message goes
    assert reply["channel"] == "telegram" and reply["channel_user_id"] == 100001
    assert reply["thread_id"] == 42
    assert reply["from_agent"] == "pi"
    print("  command backend: stdout → routed reply (channel/chat/thread from the origin) ✓")


def test_command_backend_prompt_template_and_placeholders():
    spec = A.AgentSpec(name="pi", kind="command", command=["/bin/echo", "hi"],
                       prompt_template="{agent} asked about: {body}")
    backend = A.CommandBackend(spec)
    assert backend._prompt({"body": "cake", "channel": "telegram"}) == "pi asked about: cake"
    # an unknown placeholder must not drop the human's message — it falls back to the body
    bad = A.AgentSpec(name="pi", kind="command", command=["/bin/echo"],
                      prompt_template="{nope}")
    assert A.CommandBackend(bad)._prompt({"body": "still here"}) == "still here"
    print("  prompt templates work, and a bad placeholder degrades to the raw body ✓")


def test_command_backend_survives_a_failing_agent_without_crashing_the_loop():
    spec = A.AgentSpec(name="pi", kind="command", command=["/bin/false"], timeout_s=5)
    assert A.CommandBackend(spec).dispatch(_inbound()) is None      # no reply, no crash
    missing = A.AgentSpec(name="pi", kind="command", command=["/nonexistent/agent"])
    assert A.CommandBackend(missing).dispatch(_inbound()) is None
    assert A.CommandBackend(missing).health()["ok"] is False
    print("  a failing or missing agent yields no reply and never crashes the loop ✓")


def test_output_shape_is_declared_not_guessed():
    """Agents print differently: pi chats on stdout before the answer.

    `output` is a spec field because guessing a format breaks the first time a new agent
    prints something unexpected — and the wrong guess sends chatter to the human.
    """
    spec = A.AgentSpec(name="pi", kind="command", output="last_line",
                       command=["/bin/sh", "-c", "echo 'CORTEX_RESUME session x'; echo 'the answer'"])
    reply = A.CommandBackend(spec).dispatch(_inbound("q"))
    assert reply["body"] == "the answer", reply["body"]
    print("  output=last_line skips the agent's chatter ✓")

    raw = A.AgentSpec(name="pi", kind="command", command=["/bin/sh", "-c", "printf 'line1\\nline2\\n'"])
    assert A.CommandBackend(raw).dispatch(_inbound())["body"] == "line1\nline2"
    print("  output=raw (default) keeps the whole stdout ✓")

    try:
        A.build_backends([{"name": "pi", "kind": "command", "command": ["pi"],
                           "output": "clever"}], {})
        raise AssertionError("an unknown output mode must not build")
    except ValueError as e:
        assert "output must be one of" in str(e)
        print("  an unknown output mode is refused at build ✓")


def test_bus_reply_mode_publishes_to_out_agent(monkeypatch):
    sent = {}
    import cortex_gateway.transport as T

    def _fake(bus_url, headers, queue, message):
        sent["queue"], sent["message"] = queue, message
        return {"msg_id": "x"}

    monkeypatch.setattr(T, "bus_send", _fake)
    spec = A.AgentSpec(name="pi", kind="command", command=["/bin/echo", "out:"],
                       reply_mode="bus")
    backend = A.CommandBackend(spec, bus_url="https://bus.example.com", bus_headers={})
    assert backend.dispatch(_inbound()) is None          # async: drained later
    assert sent["queue"] == "out_pi"
    msg = sent["message"]
    assert msg["subject"] == "AGENT_REPLY" and msg["from"] == "pi"
    inner = json.loads(msg["body"])
    env.validate(inner)
    assert inner["channel_user_id"] == 100001
    print("  bus reply mode publishes the routed envelope to out_<agent> ✓")
