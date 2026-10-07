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


def test_a_failed_turn_reaches_the_human_instead_of_going_quiet():
    """A turn that could not RUN must not be silent — silence reads as a dead bot.

    Live on the second bot (pi backend, 2026-10-07): a pi turn that ran past the
    spec timeout produced no message at all, so the human could not tell "the
    agent had nothing to say" from "the gateway is down". A failure is now a reply
    envelope that NAMES the reason; a turn that ran fine and printed nothing stays
    silent (that is the legitimate silent-when-clean outcome).
    """
    timed_out = A.AgentSpec(name="pi", kind="command",
                            command=["/bin/sh", "-c", "sleep 5; echo too late"],
                            timeout_s=1)
    reply = A.CommandBackend(timed_out).dispatch(_inbound())
    assert reply is not None, "a timed-out turn must not be silent"
    assert "timed out" in reply["body"], reply["body"]
    assert reply["channel_user_id"] == 100001, "a failure still routes back to the chat"

    missing = A.AgentSpec(name="pi", kind="command", command=["/nonexistent/agent"])
    reply = A.CommandBackend(missing).dispatch(_inbound())
    assert reply is not None, "an agent that cannot start must not be silent"
    assert "could not run" in reply["body"], reply["body"]

    crashed = A.AgentSpec(name="pi", kind="command",
                          command=["/bin/sh", "-c", "exit 3"], timeout_s=5)
    reply = A.CommandBackend(crashed).dispatch(_inbound())
    assert reply is not None, "a crashed agent that said nothing must not be silent"
    assert "exited 3" in reply["body"], reply["body"]
    print("  a timed-out / missing / crashed agent tells the human, never goes quiet ✓")


def test_every_shipped_backend_DECLARES_its_reply_mode():
    """The daemon must never have to guess: each shipped backend states its reply mode.

    `CommandBackend` satisfies the seam STRUCTURALLY (it does not subclass
    BackendAdapter), so a missing declaration would be invisible — the daemon's
    `getattr(..., False)` default supplies the right answer today and a changed default
    would silently flip it. Assert the declaration is on the class.
    """
    assert "async_replies" in vars(A.CommandBackend), \
        "CommandBackend must DECLARE async_replies (not rely on the daemon's default)"
    assert A.CommandBackend.async_replies is False, "a CLI agent answers inside dispatch"

    from cortex_gateway.hermes_backend import HermesBackend
    assert "async_replies" in vars(HermesBackend), \
        "HermesBackend must DECLARE async_replies (its reply arrives on the bus)"
    assert HermesBackend.async_replies is True

    built = A.CommandBackend(A.AgentSpec(name="pi", kind="command", command=["/bin/true"]))
    assert built.async_replies is False
    print("  both shipped backends declare their reply mode; neither relies on a default ✓")


def test_a_non_positive_timeout_is_refused_not_silently_defaulted():
    """`timeout_s: 0` must fail closed at build, not quietly become 300s.

    It is the field that decides when a turn is reported as timed out, and
    ``int(raw or default)`` used to swallow the explicit 0 while validate()'s "must be
    positive" never fired.
    """
    for bad in (0, -1, -0.5):
        try:
            A.build_backends([{"name": "pi", "kind": "command",
                               "command": ["/bin/true"], "timeout_s": bad}], {})
            raise AssertionError(f"timeout_s={bad} must be refused at build")
        except ValueError as e:
            assert "timeout_s must be positive" in str(e), str(e)
    assert A.AgentSpec.from_dict({"name": "pi", "timeout_s": 7}).timeout_s == 7
    assert A.AgentSpec.from_dict({"name": "pi"}).timeout_s == 300
    assert A.AgentSpec.from_dict({"name": "pi", "timeout_s": None}).timeout_s == 300
    print("  a non-positive timeout is refused; an absent one keeps the default ✓")


def test_a_partial_answer_from_a_failed_turn_is_marked_not_silently_truncated():
    """Streaming: output printed before the timeout must not look like a whole answer."""
    spec = A.AgentSpec(name="pi", kind="command", stream=True, timeout_s=1,
                       command=["/bin/sh", "-c", "echo partial answer; sleep 5"])
    seen = []
    reply = A.CommandBackend(spec).dispatch(_inbound(), sink=seen.append)
    assert reply is not None
    assert "partial answer" in reply["body"], reply["body"]
    assert "timed out" in reply["body"], \
        f"a truncated answer must say so: {reply['body']!r}"
    print("  a timed-out streamed answer is delivered WITH the failure note ✓")


def test_a_successful_turn_that_prints_nothing_is_still_silent():
    """The failure path must not turn a legitimate silent turn into a message."""
    ok = A.AgentSpec(name="pi", kind="command", command=["/bin/true"], timeout_s=5)
    assert A.CommandBackend(ok).dispatch(_inbound()) is None
    print("  a clean turn with no output is still silent ✓")


def test_command_backend_survives_a_failing_agent_without_crashing_the_loop():
    spec = A.AgentSpec(name="pi", kind="command", command=["/bin/false"], timeout_s=5)
    assert A.CommandBackend(spec).dispatch(_inbound()) is not None   # loud, no crash
    missing = A.AgentSpec(name="pi", kind="command", command=["/nonexistent/agent"])
    assert A.CommandBackend(missing).dispatch(_inbound()) is not None
    assert A.CommandBackend(missing).health()["ok"] is False
    print("  a failing or missing agent replies with the reason and never crashes the loop ✓")


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


def test_per_chat_session_continuity_is_declared_and_deterministic():
    """pi spawns per turn, so without this every message starts a blank conversation.

    The id is deterministic (hc-<agent>-<chat>) so continuity survives a gateway restart
    with no shared state, and the argv template keeps pi's flag names out of our code.
    """
    spec = A.AgentSpec(name="pi", kind="command", session="per_chat",
                       session_args=["--session-id", "{session_id}"],
                       command=["/bin/echo"])
    backend = A.CommandBackend(spec)
    reply_a = backend.dispatch(_inbound("first", chat=111))
    reply_b = backend.dispatch(_inbound("second", chat=111))
    reply_c = backend.dispatch(_inbound("other chat", chat=222))
    ids = [r["body"].split("--session-id ")[1].split()[0] for r in (reply_a, reply_b, reply_c)]
    assert ids[0] == ids[1] == "hc-pi-111", f"same chat must reuse its session: {ids}"
    assert ids[2] == "hc-pi-222", f"a different chat must get its own session: {ids}"
    print(f"  per-chat sessions are deterministic: {ids} ✓")

    off = A.AgentSpec(name="pi", kind="command", command=["/bin/echo"])
    assert "--session-id" not in A.CommandBackend(off).dispatch(_inbound("hi"))["body"]
    print("  session=none (default) spawns a fresh conversation ✓")

    for spec_dict, expect in (
        ({"name": "pi", "kind": "command", "command": ["pi"], "session": "sometimes"}, "session must be one of"),
        ({"name": "pi", "kind": "command", "command": ["pi"], "session": "per_chat",
          "session_args": ["--flag"]}, "needs '{session_id}'"),
    ):
        try:
            A.build_backends([spec_dict], {})
            raise AssertionError(f"{spec_dict} must not build")
        except ValueError as e:
            assert expect in str(e), f"expected {expect!r} in {e}"
    print("  a bad session mode, and per_chat without a session id, are refused ✓")


def test_command_backend_pins_session_identity_via_spec_env():
    """The gateway runs the agent from a deploy dir OUTSIDE any git repo.

    The harness resolves its session identity as args -> env -> git. With no env
    and no repo, that resolution COLLAPSES and every chat lands on the same
    session key — so separate conversations share one checkpoint. `env` is the
    seam that pins it, and {session_id} is already the deterministic per-chat id.
    """
    spec = A.AgentSpec(name="pi", kind="command", session="per_chat",
                       command=[sys.executable, "-c",
                                "import os;print(os.environ.get('CORTEX_SESSION_KEY',''))"],
                       env={"CORTEX_SESSION_KEY": "{session_id}"})
    backend = A.CommandBackend(spec)
    a = backend.dispatch(_inbound("first", chat=111))["body"]
    b = backend.dispatch(_inbound("second", chat=222))["body"]
    c = backend.dispatch(_inbound("third", chat=111))["body"]
    assert a == "hc-pi-111" and b == "hc-pi-222", (a, b)
    assert c == a, "the same chat must keep ONE key across turns (and restarts)"
    print(f"  spec env pins a per-chat session key: {a}, {b} ✓")


def test_spec_env_merges_the_parent_environment_and_is_validated():
    # subprocess `env=` REPLACES rather than merges, so the child must still see
    # the parent environment (a stripped PATH breaks the agent, and it reads as
    # an agent bug rather than a config bug).
    spec = A.AgentSpec(name="pi", kind="command",
                       command=[sys.executable, "-c",
                                "import os;print('has-path' if os.environ.get('PATH') else 'no-path')"],
                       env={"SOME_FLAG": "1"})
    assert A.CommandBackend(spec).dispatch(_inbound())["body"] == "has-path"
    # No env declared -> inherit normally (env=None), never an empty environment.
    plain = A.AgentSpec(name="pi", kind="command", command=[sys.executable, "-c", "print('x')"])
    assert A.CommandBackend(plain)._child_env({}, "") is None
    # A bad placeholder degrades to the literal rather than dropping the turn.
    odd = A.AgentSpec(name="pi", kind="command", command=[sys.executable, "-c", "print('x')"],
                      env={"K": "{nope}"})
    assert A.CommandBackend(odd)._child_env({}, "")["K"] == "{nope}"
    # env is a command-kind field: elsewhere it would be accepted and SILENTLY ignored.
    for bad, expect in (
        ([{"name": "e", "kind": "hermes", "env": {"A": "1"}}], "only honoured by kind 'command'"),
        ([{"name": "p", "kind": "command", "command": ["pi"], "env": {"": "1"}}], "empty key"),
    ):
        try:
            A.build_backends(bad, {"secret": "s" * 32})
            raise AssertionError(f"{bad} must not build")
        except ValueError as e:
            assert expect in str(e), f"expected {expect!r} in {e}"
    print("  env merges the parent env, degrades a bad placeholder, and is refused elsewhere ✓")


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
