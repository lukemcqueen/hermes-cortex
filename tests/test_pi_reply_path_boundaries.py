#!/usr/bin/env python3
"""The pi reply path: committed, re-runnable evidence for the claims made around it.

These began as a throwaway boundary probe run in a scratch dir during the pi parity
work (2026-10-07), and a self-adversarial review was right to refuse that: a claim
whose only support is a transcript is unverifiable the moment the transcript is gone.
The probes are therefore committed here as tests, so every claim regenerates.

What it holds:
  1. a pi-SHAPED turn (answer on stdout, the extension's chatter on stderr) delivers the
     WHOLE answer — the `output: last_line` truncation, as a test that needs no model
  2. a turn that cannot RUN reports a reason instead of going silent, and a clean turn
     with nothing to say stays silent
  3. hostile inputs (a non-string argv, no command at all, whitespace-only output) never
     crash the loop
  4. `timeout_s: 0` is refused at build rather than silently defaulted
  5. a backend whose reply-mode attribute RAISES cannot kill the poll loop
  6. the static adversarial gate reports no critical/high finding on the modules this
     claim rests on (the gate itself, re-run rather than asserted from memory)

Run: python3 -m pytest tests/test_pi_reply_path_boundaries.py -q -s
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

import gateway_envelope as env                    # noqa: E402
from cortex_gateway import agents as A            # noqa: E402
from cortex_gateway import daemon as D            # noqa: E402

# The pi CLI writes its warning/session chatter to STDERR and only the assistant answer
# to STDOUT — measured on the live install with a plain turn and with a tool-using turn.
_PI_SHAPED = (
    "echo \"1. Apple\"; echo \"2. Banana\"; echo \"3. Cherry\"; "
    "echo \"Warning: No project session found; creating a new session\" >&2; "
    "echo \"CORTEX_RESUME session facts=3\" >&2"
)


def _inbound(body="hi", chat=100001):
    return {"msg_id": env.new_msg_id(), "ts": int(time.time()), "from_agent": "",
            "to_agent": "pi", "channel": "telegram", "channel_user_id": chat,
            "thread_id": None, "body": body, "media": [], "reply_to_msg_id": None,
            "ack_required": False}


def _backend(stdout_cmd: str, **kw):
    spec = A.AgentSpec(name="pi", kind="command",
                       command=["/bin/sh", "-c", stdout_cmd], **kw)
    return A.CommandBackend(spec)


# ── 1. the whole answer survives ─────────────────────────────────────────────

def test_a_pi_shaped_turn_delivers_the_whole_multi_line_answer():
    """A 3-line answer must arrive as 3 lines — the truncation bug, without a model.

    `output: last_line` was chosen on the belief that pi prints a session line before the
    answer; measured, it does not (that line goes to stderr), so `last_line` only cut the
    answer down to its final line.
    """
    reply = _backend(_PI_SHAPED, output="raw", timeout_s=10).dispatch(_inbound())
    assert reply is not None
    assert reply["body"] == "1. Apple\n2. Banana\n3. Cherry", repr(reply["body"])
    print(f"  output=raw keeps all lines: {reply['body']!r} ✓")

    truncated = _backend(_PI_SHAPED, output="last_line", timeout_s=10).dispatch(_inbound())
    assert truncated["body"] == "3. Cherry", repr(truncated["body"])
    print("  control: output=last_line would send only the last line ✓")


# ── 2. failure is loud, silence stays silent ─────────────────────────────────

def test_a_turn_that_cannot_run_reports_why_and_a_clean_silent_turn_does_not():
    timed_out = _backend("sleep 30", output="raw", timeout_s=1).dispatch(_inbound())
    assert timed_out is not None, "a timed-out turn must not be silent"
    assert "timed out" in timed_out["body"], timed_out["body"]
    assert timed_out["channel_user_id"] == 100001, "a failure still routes to the chat"

    missing = A.CommandBackend(A.AgentSpec(name="pi", kind="command",
                                          command=["/nonexistent/agent"],
                                          timeout_s=5)).dispatch(_inbound())
    assert missing is not None and "could not run" in missing["body"], missing

    crashed = _backend("exit 3", output="raw", timeout_s=5).dispatch(_inbound())
    assert crashed is not None and "exited 3" in crashed["body"], crashed

    clean = _backend("true", output="raw", timeout_s=5).dispatch(_inbound())
    assert clean is None, "a clean turn with no output must stay silent"
    print("  timed out / missing / crashed all report; a clean silent turn stays silent ✓")


# ── 3. hostile inputs never crash the loop ───────────────────────────────────

def test_hostile_specs_produce_a_reply_never_an_exception():
    # a non-string argv entry: subprocess raises TypeError before it can exec
    bad_argv = A.CommandBackend(A.AgentSpec(name="pi", kind="command",
                                           command=["/bin/echo", 123],
                                           timeout_s=5)).dispatch(_inbound())
    assert bad_argv is not None and "could not run" in bad_argv["body"], bad_argv

    # an empty command list (bypasses build-time validation) — must not hang or crash
    empty = A.CommandBackend(A.AgentSpec(name="pi", kind="command", command=[],
                                        timeout_s=5)).dispatch(_inbound())
    assert empty is not None and "could not run" in empty["body"], empty

    # whitespace-only stdout, exit 0 → legitimately nothing to say
    blank = _backend("printf '  \\n\\n'", output="raw", timeout_s=5).dispatch(_inbound())
    assert blank is None, blank
    print("  a non-string argv, an empty command and blank output all stay handled ✓")


def test_a_non_positive_timeout_is_refused_at_build():
    for bad in (0, -1, -0.5):
        with pytest.raises(ValueError, match="timeout_s must be positive"):
            A.build_backends([{"name": "pi", "kind": "command",
                               "command": ["/bin/true"], "timeout_s": bad}], {})
    assert A.AgentSpec.from_dict({"name": "pi"}).timeout_s == 300
    assert A.AgentSpec.from_dict({"name": "pi", "timeout_s": None}).timeout_s == 300
    print("  timeout_s 0/-1/-0.5 refused; absent keeps 300 ✓")


# ── 4. a broken backend attribute cannot stop the loop ───────────────────────

def test_a_raising_reply_mode_attribute_is_read_as_synchronous():
    class Hostile:
        @property
        def async_replies(self):
            raise RuntimeError("uninitialised")

    assert D._answers_async(Hostile()) is False, "sync is the safe reading — no wedge"
    assert D._answers_async(type("A", (), {"async_replies": True})()) is True
    assert D._answers_async(object()) is False
    print("  a raising attribute reads as synchronous instead of killing the loop ✓")


def test_a_silent_sync_turn_does_not_wedge_the_chat():
    """Two messages, the first silent: the second must still be dispatched."""

    class Tr:
        def __init__(self):
            self.offset = 0
            self.sent = []

        def get_updates(self, timeout=30):
            return [{"update_id": 1, "message": {"chat": {"id": 7}, "text": "one", "date": 1}},
                    {"update_id": 2, "message": {"chat": {"id": 7}, "text": "two", "date": 1}}]

        def parse(self, raw):
            m = raw.get("message")
            if not m or not m.get("text"):
                return None
            return _inbound(m["text"], chat=7)

        def send(self, envelope):
            self.sent.append(dict(envelope))
            return True

    tr = Tr()
    gw = D.Gateway(transport=tr, backends={"pi": _backend("true", output="raw",
                                                          timeout_s=5)},
                   default_agent="pi")
    gw.poll_once()
    assert gw.inflight == {}, f"the chat was left in flight forever: {gw.inflight}"
    assert gw.queues.get(7, []) == [], f"messages stalled in the queue: {gw.queues}"
    print("  a silent turn frees the chat; nothing is left queued behind it ✓")


def test_the_typing_keeper_exists_and_refreshes_a_blocked_loop():
    """The prompt that tells the human the agent is working must survive a long turn."""
    tr = _TypingTransport()
    gw = D.Gateway(transport=tr, backends={"pi": _backend("true", timeout_s=5)},
                   default_agent="pi")
    gw.inflight[7] = {"ts": 0.0, "envelope": {"channel_user_id": 7}}
    gw.inflight[7]["typing_ts"] = 0.0

    keeper = D._TypingKeeper(gw, interval_s=0.02)
    keeper.start()
    try:
        deadline = time.time() + 3.0
        while not tr.typing and time.time() < deadline:
            time.sleep(0.02)
    finally:
        keeper.stop()
    assert tr.typing, "the keeper never refreshed the indicator for an in-flight turn"
    print(f"  keeper refreshed the indicator {len(tr.typing)}x for a blocked turn ✓")


class _TypingTransport:
    channel = "telegram"

    def __init__(self):
        self.offset = 0
        self.typing = []
        self.sent = []

    def get_updates(self, timeout=30):
        return []

    def parse(self, raw):
        return None

    def send(self, envelope):
        self.sent.append(dict(envelope))
        return True

    def send_typing(self, chat_id, thread_id=None, action="typing"):
        self.typing.append(chat_id)
        return True


# ── 5. the static gate, re-run rather than remembered ────────────────────────

def test_the_static_gate_reports_no_critical_or_high_finding():
    """Re-run the gate on the modules this claim rests on, at the level the repo requires.

    ops/scripts/manage/ and tests/ require A4; these modules are the gateway's core, so
    A4 is the honest level. The tool is the REPO copy, so this does not depend on any
    host's deployed state.
    """
    gate = _REPO / "ops" / "scripts" / "quality" / "adversarial-verify.py"
    assert gate.is_file(), f"the gate tool is missing at {gate}"
    modules = ["backend.py", "hermes_backend.py", "daemon.py", "agents.py"]
    failures = []
    for name in modules:
        target = _REPO / "ops" / "scripts" / "cortex_gateway" / name
        r = subprocess.run([sys.executable, str(gate), "--file", str(target),
                            "--level", "A4", "--gate"],
                           capture_output=True, text=True, timeout=300)
        assert "GATE_PASSED" in r.stdout or r.returncode == 0, \
            f"{name}: the gate did not pass (rc={r.returncode})\n{r.stdout[-800:]}"
        if r.returncode != 0:
            failures.append(name)
    assert not failures, f"critical/high findings in: {failures}"
    print(f"  static gate (A4) passed on {len(modules)} gateway modules ✓")