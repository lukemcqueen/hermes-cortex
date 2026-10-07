"""cortex_gateway.agents — the agent registry: adding an agent is CONFIG, not code.

The gateway's promise (ADR-0005, docs/design/cortex-gateway-parity.md) is that swapping or
adding an agent never changes the poll → dispatch → reply loop. This module is where that
promise is made mechanical: a `backend:` entry in gateway.yaml names a **kind**, the kind
names an implementation, and everything agent-specific (the command, the timeout, what the
agent can do) is DATA in the spec.

Two kinds ship today:

- ``hermes``  — the bus adapter (``inbox_<agent>`` in, ``out_<agent>`` out). An agent that
  speaks the queue contract works here, including a coding agent behind its shim.
- ``command`` — any CLI coding agent (pi, codex, claude, opencode, grok, a bespoke script).
  It is spawned per dispatch with the prompt, and its stdout becomes the reply.

Adding a THIRD kind (a hosted API, a websocket agent, a different protocol) is one class
with the four BackendAdapter methods plus one registry line — no gateway, transport,
routing or daemon change. Registering a kind is intended to be boring.

Design rules this module enforces, each because the alternative was a silent failure:

- **Unknown kind fails closed** and names the kinds that exist. A typo in gateway.yaml must
  never mean "no backend" and a swallowed message (the rehearsal lost messages exactly this
  way).
- **A spec is validated at build time**, not on first dispatch: a ``command`` kind with no
  command, an empty agent name, a reply mode that does not exist, or a non-UPPER subject is
  a startup error the operator sees, never a per-message surprise.
- **The reply's routing comes from the ORIGIN envelope** — channel, chat, thread — so the
  gateway stays the only component that knows where a message came from. An agent decides
  WHAT to say; it never decides where it goes.
"""
from __future__ import annotations

import json
import logging
import os
import select
import shlex
import subprocess
import time
from dataclasses import dataclass, field

import gateway_envelope as env

log = logging.getLogger("cortex_gateway.agents")

# ── kinds ────────────────────────────────────────────────────────────────
# kind name -> builder(spec, ctx) -> BackendAdapter. Registration is one line; a new
# coding agent is a new spec, and a new PROTOCOL is a new kind.
_KINDS: dict = {}


def register_kind(name: str):
    """Register a backend kind. The decorator exists so adding one is obvious."""
    def _wrap(fn):
        _KINDS[name] = fn
        return fn
    return _wrap


def known_kinds() -> list:
    return sorted(_KINDS)


# ── the spec ─────────────────────────────────────────────────────────────

REPLY_MODES = ("sync", "bus")

# Agents differ in what they print. `raw` takes stdout as the reply; `last_line` takes the
# final non-empty line — for an agent that chats on stdout before the answer. Measured on
# the live pi install (2026-10-07): pi's stdout IS the answer and nothing else (extension
# chatter and tool output go to its log/stderr), so `last_line` only truncated multi-line
# replies — verify an agent's stdout before choosing this, and prefer `raw`. Anything more
# involved belongs in a wrapper command in the spec, which the registry already supports.
OUTPUT_MODES = ("raw", "last_line")

# How an agent remembers the conversation. `none` = a fresh process per turn (no memory);
# `per_chat` = one agent session per human chat, declared via session_args. The id is
# DETERMINISTIC (hc-<agent>-<chat>), so continuity survives a gateway restart without
# shared state — and the argv template keeps the agent's own flag names out of our code
# (pi: --session-id, others differ).
SESSION_MODES = ("none", "per_chat")


def _positive_or_default(raw, default: int) -> int:
    """`timeout_s` from config: absent → the default; present → coerced, then validated.

    ``int(raw or default)`` silently turned an explicit ``0`` into the default, so a
    config saying ``timeout_s: 0`` quietly got 300s while ``validate()``'s "must be
    positive" never fired — a fail-open in the very field that decides how long a turn
    may run (and therefore when a turn is reported as timed out).
    """
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass
class AgentSpec:
    """Everything agent-specific, as DATA (gateway.yaml ``backends:`` entry)."""

    name: str
    kind: str = "hermes"
    command: list = field(default_factory=list)   # kind=command
    prompt_template: str = "{body}"               # what the agent is asked
    timeout_s: int = 300
    reply_mode: str = "sync"                      # sync (return) | bus (write out_<agent>)
    output: str = "raw"                           # raw | last_line (agents print chatter)
    session: str = "none"                         # none | per_chat (one agent session per chat)
    session_args: list = field(default_factory=lambda: ["--session-id", "{session_id}"])
    stream: bool = False                          # kind=command: show output as it arrives
    capabilities: list = field(default_factory=list)  # free-form, for operators/health
    model: str = ""
    subject: str = "USER_MESSAGE"                 # kind=hermes inbound subject
    # kind=command: extra env for the child process, templated like prompt_template
    # ({session_id}, {agent}, {channel}, {user}, {body}, {model}).
    # Load-bearing for session identity: a harness started OUTSIDE a git repo (the
    # gateway runs pi from its deploy dir) cannot derive repo/branch, so without a
    # pinned key every chat falls back to ONE session key and they share a
    # checkpoint. That is a data-correctness bug, not a cosmetic one.
    env: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(d: dict) -> "AgentSpec":
        if isinstance(d, str):                     # shorthand: "esther" / "pi"
            return AgentSpec(name=d)
        if not isinstance(d, dict):
            raise ValueError(f"backend spec must be a mapping or a name, got {type(d).__name__}")
        allowed = {"name", "kind", "command", "prompt_template", "timeout_s", "reply_mode",
                   "capabilities", "model", "subject", "output", "session", "session_args",
                   "stream", "env", "extra"}
        unknown = set(d) - allowed
        if unknown:
            raise ValueError(
                f"backend spec has unknown key(s): {sorted(unknown)}. "
                f"Allowed: {sorted(allowed)}")
        cmd = d.get("command", [])
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        return AgentSpec(
            name=str(d.get("name", "")).strip(),
            kind=str(d.get("kind", "hermes")).strip().lower(),
            command=list(cmd or []),
            prompt_template=str(d.get("prompt_template") or "{body}"),
            timeout_s=_positive_or_default(d.get("timeout_s"), 300),
            reply_mode=str(d.get("reply_mode", "sync")).strip().lower(),
            output=str(d.get("output", "raw")).strip().lower(),
            session=str(d.get("session", "none")).strip().lower(),
            session_args=list(d.get("session_args") or ["--session-id", "{session_id}"]),
            stream=bool(d.get("stream", False)),
            capabilities=list(d.get("capabilities", []) or []),
            model=str(d.get("model", "") or ""),
            subject=str(d.get("subject", "USER_MESSAGE") or "USER_MESSAGE"),
            env={str(k): str(v) for k, v in (d.get("env") or {}).items()},
            extra=dict(d.get("extra", {}) or {}),
        )

    def validate(self) -> None:
        """Fail at BUILD time with a message an operator can act on."""
        if not self.name:
            raise ValueError("backend spec: 'name' is required (it becomes inbox_/out_ queue names)")
        if self.kind not in _KINDS:
            raise ValueError(
                f"backend '{self.name}': unknown kind {self.kind!r}. "
                f"Known kinds: {known_kinds()}. Add one with register_kind().")
        if self.kind == "command" and not self.command:
            raise ValueError(
                f"backend '{self.name}': kind 'command' needs a 'command' "
                f"(e.g. command: [pi, --model, openrouter/moonshotai/kimi-k2.6])")
        if self.reply_mode not in REPLY_MODES:
            raise ValueError(
                f"backend '{self.name}': reply_mode must be one of {REPLY_MODES}, "
                f"got {self.reply_mode!r}")
        if self.output not in OUTPUT_MODES:
            raise ValueError(
                f"backend '{self.name}': output must be one of {OUTPUT_MODES}, "
                f"got {self.output!r}")
        if self.session not in SESSION_MODES:
            raise ValueError(
                f"backend '{self.name}': session must be one of {SESSION_MODES}, "
                f"got {self.session!r}")
        if self.session == "per_chat" and not any("{session_id}" in a for a in self.session_args):
            raise ValueError(
                f"backend '{self.name}': session='per_chat' needs '{{session_id}}' somewhere "
                f"in session_args (got {self.session_args}) — otherwise every chat shares one "
                "session, which is not what 'per_chat' says")
        if not self.subject or self.subject != self.subject.upper():
            raise ValueError(
                f"backend '{self.name}': subject must be UPPER_CASE "
                f"(the bus rejects anything else), got {self.subject!r}")
        if self.timeout_s <= 0:
            raise ValueError(f"backend '{self.name}': timeout_s must be positive")
        # `env` is a command-kind field. On another kind it would be accepted and
        # then silently ignored — the failure mode this module exists to stop.
        for key in self.env:
            if not str(key).strip():
                raise ValueError(f"backend '{self.name}': env has an empty key")
        if self.env and self.kind != "command":
            raise ValueError(
                f"backend '{self.name}': 'env' is only honoured by kind 'command' "
                f"(got {self.kind!r}) — it would be accepted and silently ignored")


# ── reply routing (the one rule every backend shares) ────────────────────

def reply_from_origin(origin: dict, body: str, *, agent: str) -> dict:
    """Build a reply envelope whose ROUTING is copied from the origin envelope.

    channel / channel_user_id / thread_id come from the inbound message because only the
    gateway saw the human. An agent supplies the text; where it goes is not its decision.
    """
    if not str(body or "").strip():
        raise ValueError("reply_from_origin: refusing to build an empty reply")
    return {
        "msg_id": env.new_msg_id(),
        "ts": int(time.time()),
        "from_agent": agent,
        "to_agent": str(origin.get("to_agent", "")),
        "channel": str(origin.get("channel", "")),
        "channel_user_id": origin.get("channel_user_id"),
        "thread_id": origin.get("thread_id"),
        "body": body,
        "media": [],
        # ANCHOR: in a topic, anchor the answer to the message that triggered it, so a busy
        # topic shows which question each reply belongs to (the incumbent anchors too).
        # Outside a topic the anchor is only set when the human themselves replied to
        # something — quoting every DM would be noise.
        "reply_to_msg_id": (origin.get("tg_msg_id") if origin.get("thread_id")
                            else origin.get("reply_to_msg_id")),
        "ack_required": False,
    }


def publish_reply(bus_url: str, bus_headers: dict, agent: str, reply: dict) -> bool:
    """Write a reply envelope to out_<agent> for the gateway to drain.

    The bus message schema differs from the envelope (see docs/design/gateway-reply-path.md):
    the envelope rides inside the message's `body`, `from` must be the authenticated agent,
    and the subject is an UPPER_CASE protocol name.
    """
    from . import transport as _bus
    env.validate(reply)
    message = {
        "subject": "AGENT_REPLY",
        "body": json.dumps(reply),
        "from": agent,
        "to": agent,
        "priority": 0,
        "correlation_id": str(reply.get("msg_id", "")),
    }
    return bool(_bus.bus_send(bus_url, bus_headers, f"out_{agent}", message))


# ── kinds ────────────────────────────────────────────────────────────────

@register_kind("hermes")
def _build_hermes(spec: AgentSpec, ctx: dict):
    """The bus adapter: an agent (or its shim) speaks inbox_/out_ on the queue."""
    from .hermes_backend import HermesBackend
    if not ctx.get("secret"):
        raise ValueError(
            f"backend '{spec.name}': GATEWAY_SECRET is required — every inbound envelope "
            "is HMAC-signed, and an empty key makes the signature forgeable")
    os.environ.setdefault("GATEWAY_INBOUND_SUBJECT", spec.subject)
    backend = HermesBackend(agent=spec.name, bus_url=ctx.get("bus_url", ""),
                            bus_headers=ctx.get("bus_headers", {}), secret=ctx["secret"])
    backend.spec = spec            # operators/health can see what was declared
    return backend


class CommandBackend:
    """Any CLI coding agent, driven by config: prompt in, reply envelope out.

    This is the generic door for "a different agent with different functions": the command
    line, its timeout and how it answers are spec fields, so pi / codex / claude / opencode
    / a bespoke script are all the same class plus a config entry.
    """

    def __init__(self, spec: AgentSpec, *, bus_url: str = "", bus_headers: dict | None = None):
        self.spec = spec
        self.bus_url = bus_url
        self.bus_headers = bus_headers or {}

    # -- BackendAdapter surface ------------------------------------------------
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        exe = self.spec.command[0] if self.spec.command else ""
        found = bool(exe) and (os.path.isabs(exe) and os.access(exe, os.X_OK) or bool(_which(exe)))
        return {"ok": found, "backend": "command", "agent": self.spec.name,
                "command": self.spec.command[:1], "capabilities": self.spec.capabilities}

    # A backend that can report partial output advertises it, so the gateway only builds a
    # sink for an agent that will use one.
    supports_stream = True

    def dispatch(self, envelope: dict, sink=None):
        if not isinstance(envelope, dict):
            return None
        try:
            inbound = env.validate(envelope)
        except env.EnvelopeError:
            return None                       # malformed — DLQ, never crash the loop
        prompt = self._prompt(inbound)
        session_id = self._session_id(inbound)
        child_env = self._child_env(inbound, session_id)
        # STREAMING (opt-in per spec): report partial output as it is produced, so a long
        # coding turn is visible instead of silent. The sink is the GATEWAY's (it owns
        # formatting and delivery); a backend that can stream advertises supports_stream.
        if sink is not None and self.spec.stream:
            out, failure = self._run_streaming(prompt, session_id, sink, child_env)
        else:
            out, failure = self._run(prompt, session_id, child_env)
        if failure:
            # The turn could not RUN (in full). Saying nothing here is indistinguishable
            # from a dead gateway — measured live: a pi turn that ran past its timeout
            # produced no message at all, so the human could not tell "nothing to say"
            # from "broken". When the agent did print part of an answer before failing,
            # the note is appended so partial output can never look complete.
            note = self._failure_text(failure)
            out = f"{out}\n\n{note}" if out.strip() else note
        elif not out:
            return None                       # a clean turn with nothing to say is legitimate
        reply = reply_from_origin(inbound, out, agent=self.spec.name)
        if self.spec.reply_mode == "bus":
            ok = publish_reply(self.bus_url, self.bus_headers, self.spec.name, reply)
            if not ok:
                log.warning(
                    "command backend %s: could not publish the reply to out_%s — the reply "
                    "was NOT delivered (check the bus URL and the out_%s ACL)",
                    self.spec.name, self.spec.name, self.spec.name)
            return None                       # async: the gateway drains it
        return env.validate(reply)            # sync: the daemon sends it now

    def _failure_text(self, failure: str) -> str:
        """Tell the human WHY the turn produced nothing. Never a silent failure."""
        return (f"⚠️ {self.spec.name} could not answer: {failure}. "
                "Your message was received — send it again to retry.")

    def poll_replies(self, max_n: int = 5) -> list:
        return []                             # sync mode answers inside dispatch

    # -- internals -------------------------------------------------------------
    def _prompt(self, inbound: dict) -> str:
        try:
            return self.spec.prompt_template.format(
                body=inbound.get("body", ""), agent=self.spec.name,
                channel=inbound.get("channel", ""),
                user=inbound.get("channel_user_id", ""),
                model=self.spec.model)
        except (KeyError, IndexError):
            # A bad template is a config error, not a message error: fall back to the body
            # and say so, rather than dropping the human's message.
            log.warning("command backend %s: prompt_template has an unknown placeholder; "
                        "using the raw body", self.spec.name)
            return str(inbound.get("body", ""))

    def _session_id(self, inbound: dict) -> str:
        """Deterministic per-chat session id: stable, no shared state, restart-safe.

        hc-<agent>-<chat> — pi creates the session if it does not exist, so the first turn
        of a chat starts one and every later turn continues it. A random or in-memory id
        would silently reset the conversation on every gateway restart.

        The gateway may publish a `session_generation` (its `/new` command). Generation
        0 is the chat's original session and keeps the UNSUFFIXED id, so a chat that has
        never used `/new` looks exactly as it did before this existed — no migration and
        no lost history. Generation N appends `-g<N>`, giving `/new` a fresh session while
        the earlier ones stay on disk under their own ids (archive, not delete).
        """
        if self.spec.session != "per_chat":
            return ""
        chat = inbound.get("channel_user_id")
        if chat is None:
            return ""
        base = f"hc-{self.spec.name}-{chat}"
        generation = inbound.get("session_generation") or 0
        # bool is an int subclass; True must not read as generation 1.
        if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
            return base
        return f"{base}-g{generation}"

    def session_id_for(self, inbound: dict) -> str:
        """The session id this backend WOULD use for an envelope (read-only).

        The gateway calls this to NAME the conversation it is archiving in its `/new`
        reply, so the transcript is discoverable without reading this module.
        """
        return self._session_id(inbound)

    def _argv(self, prompt: str, session_id: str = "") -> list:
        cmd = [*self.spec.command]
        if session_id:
            cmd += [str(a).replace("{session_id}", session_id) for a in self.spec.session_args]
        cmd.append(prompt)
        return cmd

    def _child_env(self, inbound: dict, session_id: str = "") -> dict | None:
        """The child's environment: the spec's `env`, templated, over the parent's.

        Returns None when the spec declares nothing, so the child inherits
        normally. When it DOES declare env, the whole environment is passed
        explicitly (parent + overrides): `env=` REPLACES rather than merges, and
        handing a child a stripped environment breaks it in ways that read as an
        agent bug instead of a config bug.

        This is the seam that pins session identity. The harness resolves
        harness/repo/branch from its cwd when nothing is set, and the gateway's
        cwd is a deploy dir outside any git repo — so the resolution collapses and
        every chat lands on ONE session key. Declaring
        `env: {"CORTEX_SESSION_KEY": "{session_id}"}` makes each chat its own.
        """
        if not self.spec.env:
            return None
        vals = {
            "body": str(inbound.get("body", "")),
            "agent": self.spec.name,
            "channel": str(inbound.get("channel", "")),
            "user": str(inbound.get("channel_user_id", "")),
            "model": self.spec.model,
            "session_id": session_id,
        }
        overrides: dict = {}
        for key, raw in self.spec.env.items():
            try:
                overrides[str(key)] = str(raw).format(**vals)
            except (KeyError, IndexError):
                # A bad placeholder is a config error, not a message error: pass it
                # through and say so rather than dropping the turn.
                log.warning("command backend %s: env %s has an unknown placeholder; "
                            "passing it verbatim", self.spec.name, key)
                overrides[str(key)] = str(raw)
        return {**os.environ, **overrides}

    def _run(self, prompt: str, session_id: str = "",
             child_env: dict | None = None) -> tuple[str, str]:
        """Run one turn → ``(reply_text, failure_reason)``.

        ``failure_reason`` is "" when the agent RAN. It names the problem when the turn
        could not run at all (timeout, exec error, a crash that printed nothing), which
        the caller turns into a visible reply — a silent failure reads as a dead bot.
        """
        cmd = self._argv(prompt, session_id)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.spec.timeout_s, env=child_env)
        except subprocess.TimeoutExpired:
            log.warning("command backend %s: timed out after %ss — reporting the "
                        "failure to the human", self.spec.name, self.spec.timeout_s)
            return "", f"timed out after {self.spec.timeout_s}s"
        except (OSError, ValueError, TypeError) as e:
            # OSError = cannot spawn; ValueError/TypeError = an unusable argv from a
            # bad spec (e.g. a non-string entry). Never let a config typo kill the loop.
            log.warning("command backend %s: could not run %r (%s)",
                        self.spec.name, self.spec.command[:1], e)
            return "", f"could not run {self.spec.command[:1]} ({e})"
        out = self._shape_output(proc.stdout or "")
        if proc.returncode != 0:
            log.warning("command backend %s: exit %s; stderr=%r",
                        self.spec.name, proc.returncode, (proc.stderr or "")[:200])
            if not out:
                return "", f"exited {proc.returncode} with no output"
        return out, ""

    def _run_streaming(self, prompt: str, session_id: str, sink,
                       child_env: dict | None = None) -> tuple[str, str]:
        """Run the agent, reporting accumulated stdout as it arrives.

        Line-buffered reading with a best-effort sink: a sink failure (say, a rate-limited
        edit) must not abort the turn — the final text still comes back through dispatch and
        the gateway delivers it normally. Returns ``(reply_text, failure_reason)``.
        """
        cmd = self._argv(prompt, session_id)
        acc: list = []
        failure = ""
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                    env=child_env)
        except (OSError, ValueError, TypeError) as e:
            log.warning("command backend %s: could not start %r (%s)",
                        self.spec.name, self.spec.command[:1], e)
            return "", f"could not run {self.spec.command[:1]} ({e})"
        try:
            stream = proc.stdout
            if stream is not None:
                if self._drain_stream(stream, sink, acc):
                    # The DEADLINE hit while reading: the agent had the pipe open and
                    # was still talking (or hung). Report it — partial output must
                    # never be presented as a complete answer.
                    failure = f"timed out after {self.spec.timeout_s}s"
            if not failure:
                proc.wait(timeout=self.spec.timeout_s)
        except subprocess.TimeoutExpired:
            log.warning("command backend %s: timed out after %ss (streaming)",
                        self.spec.name, self.spec.timeout_s)
            failure = f"timed out after {self.spec.timeout_s}s"
        finally:
            if proc.poll() is None:
                proc.kill()
        out = self._shape_output("".join(acc))
        if not out and not failure and proc.returncode not in (0, None):
            failure = f"exited {proc.returncode} with no output"
        return out, failure

    def _drain_stream(self, stream, sink, acc: list) -> bool:
        """Accumulate stdout lines until EOF or the spec deadline. True = deadline hit.

        `timeout_s` must bound the READ, not just the final wait: the previous version
        read with a plain ``for line in stream`` and applied the timeout only to the
        closing ``wait()``, so a streaming agent that kept its pipe open (a hung turn)
        was never bounded at all — the gateway would block on it indefinitely.
        """
        deadline = time.monotonic() + self.spec.timeout_s
        use_select = True
        while True:
            if use_select:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return True
                try:
                    ready, _, _ = select.select([stream], [], [], min(remaining, 1.0))
                except (OSError, ValueError):   # no select on this pipe/platform
                    use_select = False
                    continue
                if not ready:
                    continue
            line = stream.readline()
            if not line:
                return False                    # EOF — the agent finished on its own
            acc.append(line)
            try:
                sink(self._shape_output("".join(acc)))
            except Exception as e:  # noqa: BLE001 — UX only, never the turn
                log.debug("stream sink failed: %s", e)

    def _shape_output(self, stdout: str) -> str:
        """Turn the agent's stdout into the reply text (spec-declared, never guessed)."""
        text = (stdout or "").strip()
        if self.spec.output == "last_line":
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            return lines[-1] if lines else ""
        return text


@register_kind("command")
def _build_command(spec: AgentSpec, ctx: dict):
    return CommandBackend(spec, bus_url=ctx.get("bus_url", ""),
                          bus_headers=ctx.get("bus_headers", {}))


def _which(exe: str) -> str:
    import shutil
    return shutil.which(exe) or ""


# ── the factory (what the daemon calls) ──────────────────────────────────

def build_backends(specs: list, ctx: dict) -> dict:
    """authoritative: gateway.yaml ``backends:`` → {agent_name: BackendAdapter}.

    Every spec is validated before any backend is built, so one bad entry is a startup
    error naming that entry — never a half-wired gateway that silently drops messages.
    """
    parsed = [AgentSpec.from_dict(s) for s in specs]
    if not parsed:
        # An empty backends list is legitimate and documented: a gateway that only drains
        # outbound (or one mid-migration with no inbound agent yet). Returning {} keeps that
        # door open — the previous implementation did, and test_cortex_gateway_key_guard
        # asserts it, including that the GATEWAY_SECRET guard is skipped when there is no
        # inbound backend to sign for.
        log.info("backends built: {} (none configured — outbound-only)")
        return {}
    names = [s.name for s in parsed]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate backend name(s): {sorted(dupes)} — names become queue "
                         "names, so they must be unique")
    for s in parsed:
        s.validate()
    out = {}
    for s in parsed:
        try:
            out[s.name] = _KINDS[s.kind](s, ctx)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 — surface the entry, never a bare crash
            raise ValueError(f"backend '{s.name}' (kind {s.kind}) failed to build: {e}") from e
    log.info("backends built: %s", {n: b.spec.kind for n, b in out.items()})
    return out
