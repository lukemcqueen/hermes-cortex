"""cortex_gateway.daemon — the standalone gateway daemon (CR3).

Wires the two seams into the full poll → dispatch → reply loop:

    Telegram poll (transport) → parse → route → BackendAdapter.dispatch
        → sync reply → transport.send
    drain_outbound: BackendAdapter.poll_replies → transport.send  (async)

This is `msg-gateway.py`'s `Gateway.poll_bot()` + `drain_outbound()` pattern
with the dispatch/reply step inserted between poll and drain — the difference
is that agent dispatch now goes through the BackendAdapter seam instead of
being hard-wired to the bus. hermes is the first backend; pi and steadfaste
plug in via `backends={name: BackendAdapter}` with zero changes here.

Invariants kept from msg-gateway.py (party-converged):
  - enqueue-then-ack: offset advances ONLY after a turn completes (send or
    silent), never on a failed dispatch.
  - routing lives here (channel_user_id → agent), never in transport/backend.
  - gateway is the ONLY getUpdates consumer per bot (bot_locks on run_locked).

Parity slice 2 (G5/G6/G7, 2026-10-02) — the incumbent's daemon-side behaviour:
  - G5 slash commands: /stop and /status are handled here; /stop is ALSO
    forwarded so the agent can stop the work it started; every other command is
    forwarded with tg_kind="command" rather than becoming prompt prose.
  - G6 busy/interrupt: one in-flight turn per chat, arrivals queue behind it
    (bounded), and /stop clears the queue and suppresses that chat's pending
    replies until the next human message.
  - G7 polling recovery: transient poll errors back off exponentially instead of
    spinning; a conflict stands by, and only PERSISTENT conflicts exit (a real
    second poller must not have its updates stolen).

Slash-command parity for a CLI agent (2026-10-08). Four commands are the ones a
human actually reaches for, and NONE of them can be forwarded to a `kind: command`
agent: pi handles its built-in slash commands only in the interactive/RPC surfaces,
so `/new`, `/model`, `/compact` and `/restart` as prompt text become four
characters of conversation and nothing more. They are therefore gateway-level:

  - `/new`      rotation of the session id (archive, never delete) — sessions.py
  - `/model`    per-chat model override, published on the envelope the backend
                builds its argv from — models.py
  - `/compact`  a session operation, run through the backend's declared control
                command (`commands.compact` in gateway.yaml) — pi speaks RPC
  - `/restart`  exit + `Restart=always`, refused when not systemd-supervised.
                The chat is MARKED (restarts.py) so the first reply after the
                restart carries a one-line confirmation and the agent is told the
                same fact with its prompt — otherwise the only available answer to
                "did you restart?" comes from an agent whose session survived, and
                it says no. Measured 2026-10-08.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # runtime import stays lazy (pairing is opt-in)
    from .models import ModelBook
    from .pairing import PairingStore
    from .restarts import RestartBook
    from .sessions import SessionBook

if __package__ in (None, ""):
    # Run as a script (python3 daemon.py / systemd ExecStart): make the
    # package importable so the relative imports below resolve. Imported as a
    # module (python3 -m cortex_gateway.daemon / from cortex_gateway.daemon)
    # this branch is skipped.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "cortex_gateway"

from .transport import (DEFAULT_POLL_SECONDS, BotConfig, PollingConflict,
                        TransportAdapter, TelegramAdapter)

DEFAULT_BACKEND_AGENT = "hermes"

# The post-restart confirmation. Wording chosen by the operator (Luke, 2026-10-08):
# short, in the chat's voice, and it answers the two questions the restart raises —
# did it work, and did I lose the conversation. Sent by the NEW process at startup
# (so it arrives without the human having to say anything), and used as the footer
# on the first reply when that send could not be delivered.
RESTART_CONFIRMATION = "♻ Gateway restarted successfully. Your session continues."


def _as_chat_id(chat):
    """A marker's chat key back to the id type the transport expects.

    The book is JSON, so keys are strings; Telegram wants the int. A non-numeric
    key is passed through rather than dropped — the transport knows its own ids.
    """
    try:
        return int(str(chat))
    except ValueError:
        return chat


def _answers_async(backend) -> bool:
    """True when this backend's reply arrives LATER (poll_replies), not in dispatch.

    Declared by the backend (`async_replies`), never inferred from a None reply:
    a synchronous CLI agent returns None when it had nothing to say, and treating
    that as "still waiting" wedges the chat permanently.

    A backend whose attribute RAISES (a property touching uninitialised state) is
    reported and read as synchronous: sync is the safe direction — it frees the chat
    instead of leaving it waiting forever — whereas letting the exception out would
    kill the poll loop and take every chat with it.
    """
    try:
        return bool(getattr(backend, "async_replies", False))
    except Exception as e:  # noqa: BLE001 — never let one backend's attribute stop the loop
        print(f"⚠️  backend {type(backend).__name__}.async_replies raised ({e}); "
              f"treating it as synchronous", file=sys.stderr)
        return False


class _TypingKeeper(threading.Thread):
    """Keep the "typing…" prompt alive while the poll loop is BLOCKED in a turn.

    The loop is single-threaded, so a synchronous backend (a CLI agent) blocks
    inside dispatch for the whole turn and ``Gateway._refresh_typing()`` — called
    once per poll cycle — never runs. Telegram clears a chat action after ~5s, so
    on the second bot a long pi turn showed NO typing prompt at all, while the
    hermes backend (async, returns immediately) kept it alive. UX only: every call
    is best-effort and a failure can never affect delivery.
    """

    def __init__(self, gateway, interval_s: float = 4.0):
        super().__init__(daemon=True, name="cortex-gateway-typing")
        self.gateway = gateway
        self.interval_s = interval_s
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.gateway._refresh_typing()
            except Exception as e:  # noqa: BLE001 — UX must never kill the loop
                print(f"⚠️  typing keeper: {e}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()


class _Streamer:
    """Show a turn's progress by editing ONE message (never a message per partial).

    Throttled because Telegram rate-limits edits: a partial every line would be rejected and
    would also be unreadable. On any failure it gives up (failed=True) and the final text is
    delivered normally — streaming is a courtesy, never the delivery path.
    """

    MIN_INTERVAL_S = 1.5

    def __init__(self, gateway, chat, envelope):
        self.gw = gateway
        self.chat = chat
        self.thread_id = (envelope or {}).get("thread_id")
        self.message_id = None
        self.last_sent = ""
        self.last_at = 0.0
        self.failed = False

    @property
    def streamed(self) -> bool:
        return self.message_id is not None and not self.failed

    def partial(self, text: str) -> None:
        if self.failed or not text or text == self.last_sent:
            return
        now = time.time()
        if now - self.last_at < self.MIN_INTERVAL_S:
            return
        self.last_at = now
        self.last_sent = text
        tr = self.gw.transport
        if self.message_id is None:
            send_text = getattr(tr, "send_text", None)
            if not send_text:
                self.failed = True
                return
            self.message_id = send_text(self.chat, text, self.thread_id)
            if self.message_id is None:
                self.failed = True
        elif not tr.edit_message(self.chat, self.message_id, text):
            self.failed = True

    def finish(self, final_text: str) -> bool:
        """True when the streamed message already carries the final text (do not resend)."""
        if not self.streamed:
            return False
        if not final_text or final_text == self.last_sent:
            return True
        return bool(self.gw.transport.edit_message(self.chat, self.message_id, final_text))


class Gateway:
    """The decoupled gateway daemon. Transport ↔ BackendAdapter."""

    def __init__(self, transport: TransportAdapter, backends: dict,
                 default_agent: str = DEFAULT_BACKEND_AGENT,
                 routing_overrides: dict | None = None,
                 allowed_users: set | None = None,
                 pairing: "PairingStore | None" = None,
                 sessions: "SessionBook | None" = None,
                 models: "ModelBook | None" = None,
                 restarts: "RestartBook | None" = None):
        self.transport = transport
        self.backends = backends          # agent_name -> BackendAdapter
        self.default_agent = default_agent
        self.routing_overrides = routing_overrides or {}
        # Sender allowlist (TELEGRAM_ALLOWED_USERS). None means "not gated
        # here" — build_gateway requires it, so production is never None.
        self.allowed_users = allowed_users
        # DM pairing (opt-in): an unknown sender can request enrolment, but their message
        # is NEVER dispatched until an already-allowed user approves the code.
        self.pairing = pairing
        # Per-chat session generations (/new). None = rotation not configured, in
        # which case a chat keeps one session forever (the behaviour before /new).
        self.sessions = sessions
        # Per-chat model overrides (/model). None = switching not configured, in
        # which case every chat runs the backend's configured default.
        self.models = models
        # Unseen /restart markers: the gateway cannot tell a human it restarted
        # AFTER it restarted, so the first reply once it is back does.
        self.restarts = restarts
        # offset tracks the transport's own offset (transport owns the truth).
        self.offset = getattr(transport, "offset", 0)

        # ── per-chat turn state (G5/G6: slash dispatch, busy/interrupt) ────
        # A turn is IN FLIGHT from dispatch until its reply is drained. The
        # incumbent serializes turns per chat and lets /stop interrupt; the
        # target fired every message straight at the agent with no state at
        # all. Now: one in-flight turn per chat, arrivals queue behind it, and
        # /stop clears both the pending replies and the queue.
        self.inflight: dict = {}      # chat_id -> {"ts": float, "envelope": dict}
        self.queues: dict = {}        # chat_id -> [envelope, ...]
        self.suppressed: set = set()  # chat_id -> drop replies until next user msg
        self.max_queue = int(os.environ.get("GATEWAY_MAX_QUEUE_PER_CHAT", "5") or 5)

        # ── poll health (G7: recovery) ──────────────────────────────
        self.consecutive_failures = 0
        self.consecutive_conflicts = 0
        self.max_conflicts = int(os.environ.get("GATEWAY_MAX_POLL_CONFLICTS", "3") or 3)

    # ── routing ────────────────────────────────────────────────
    def route(self, chat_id) -> str:
        if chat_id is not None and str(chat_id) in self.routing_overrides:
            return str(self.routing_overrides[str(chat_id)])
        return self.default_agent

    # ── one inbound poll cycle ─────────────────────────────────
    def poll_once(self) -> None:
        """getUpdates → parse → route → (command | dispatch) → reply."""
        try:
            updates = self.transport.get_updates(timeout=30)
        except (urllib.error.HTTPError, PollingConflict) as e:
            code = getattr(e, "code", None)
            if isinstance(e, PollingConflict) or code == 409:
                self._note_conflict(e)
                return
            self.consecutive_failures += 1
            print(f"⚠️  getUpdates HTTP {code} ({self.consecutive_failures} in a "
                  f"row) — backing off {self._poll_delay():.0f}s", file=sys.stderr)
            return
        except Exception as e:
            self.consecutive_failures += 1
            print(f"⚠️  poll error ({self.consecutive_failures} in a row): {e} "
                  f"— backing off {self._poll_delay():.0f}s", file=sys.stderr)
            return

        self.consecutive_failures = 0
        self.consecutive_conflicts = 0
        for upd in updates:
            uid = upd.get("update_id")
            if uid is None:
                continue
            self._turn(upd)
            self.offset = max(self.offset, uid + 1)
            # Persist through the transport when it supports it (Telegram does), so a
            # restart resumes at the last CONSUMED update instead of re-reading from
            # initial_offset. Falls back to the bare attribute for a transport that
            # has an offset but nowhere to keep it.
            _set_offset = getattr(self.transport, "set_offset", None)
            if _set_offset is not None:
                _set_offset(self.offset)
            elif hasattr(self.transport, "offset"):
                self.transport.offset = self.offset

    def _turn(self, raw: dict) -> None:
        """One app event → parse → route → (command | dispatch) → reply."""
        envelope = self.transport.parse(raw)
        if envelope is None:
            return
        if self.allowed_users is not None:
            sender = str(envelope.get("channel_user_id"))
            if not self._sender_allowed(sender):
                if self.pairing is not None:
                    # Enrolment path: reply with a code, tell the owner, and DISPATCH
                    # NOTHING. The agent must never see an unpaired sender's text.
                    self._pair_request(envelope, sender)
                    return
                print(f"⛔ dropped sender {sender} — not in "
                      "TELEGRAM_ALLOWED_USERS", file=sys.stderr)
                return
        chat = envelope.get("channel_user_id")
        # Publish the chat's session generation BEFORE any dispatch, so the backend
        # derives the right session id. `/new` bumps it (see _handle_new) and this is
        # read per message, so every later turn picks up the new generation while an
        # envelope already queued keeps the one it was sent under.
        if self.sessions is not None:
            envelope["session_generation"] = self.sessions.generation(chat)
        # Publish the chat's MODEL override the same way, and for the same reason: the
        # backend builds the argv, so "which model answers this chat" has to travel with
        # the envelope. Empty string = the backend's configured default.
        if self.models is not None:
            envelope["model_override"] = self.models.get(chat)
        # If this chat pressed /restart and has not been told yet, hand the FACT to
        # the agent as well: the session survived the restart, so an agent asked
        # "did you restart?" otherwise answers "no" — truthfully about the session,
        # wrongly about the gateway, and it is the only answer the human can get.
        if self.restarts is not None and envelope.get("tg_kind") == "message":
            notice = self.restarts.pending(chat)
            if notice:
                envelope["restart_notice"] = notice.get("ts")
                # Only when the gateway could NOT announce it at startup does the
                # first reply have to carry the news itself.
                if not notice.get("announced"):
                    envelope["restart_footer"] = notice.get("ts")
        # A new human message lifts a previous /stop suppression.
        if envelope.get("tg_kind") == "message":
            self.suppressed.discard(chat)
        # A button press: clear its spinner immediately. The agent decides what the choice
        # MEANS; the gateway only acknowledges that it was received (best-effort).
        if envelope.get("tg_kind") == "callback":
            self._answer_callback(envelope)
        envelope["to_agent"] = self.route(chat)
        backend = self.backends.get(envelope["to_agent"])
        if backend is None:
            print(f"⚠️  no backend for agent {envelope['to_agent']}",
                  file=sys.stderr)
            return

        command = self._command_of(envelope)
        if command is not None and self._handle_command(command, envelope, backend):
            return

        self._dispatch_or_queue(chat, envelope, backend)

    # ── slash commands (G5) ────────────────────────────────────
    @staticmethod
    def _command_of(envelope: dict):
        """`/stop`, `/stop@MyBot `, or None. Only a leading token counts."""
        body = (envelope.get("body") or "").strip()
        if not body.startswith("/") or len(body) < 2:
            return None
        return body.split()[0].split("@")[0].lower()

    def _handle_command(self, command: str, envelope: dict, backend) -> bool:
        """Handle a gateway-level command. True = consumed (do not dispatch again)."""
        chat = envelope.get("channel_user_id")
        if command in ("/approve", "/deny") and self.pairing is not None:
            return self._handle_pair_command(command, envelope)
        if command == "/stop":
            dropped = self._interrupt(chat)
            # ALSO forward it: the gateway can drop a pending reply, but only the
            # agent can stop work it has already started. tg_kind marks it as a
            # command so it is never mistaken for a prompt.
            self._forward(envelope, backend)
            self._reply(chat, f"🛑 /stop sent to {envelope.get('to_agent')}; "
                              f"dropped {dropped} queued message(s)")
            return True
        if command == "/status":
            self._reply(chat, self._status_line())
            return True
        if command == "/help":
            self._reply(chat, "gateway commands: /stop · /status · /help · /new · "
                              "/model · /compact · /restart — anything else is "
                              "forwarded to the agent")
            return True
        if command == "/new":
            return self._handle_new(chat, envelope, backend)
        if command == "/model":
            return self._handle_model(chat, envelope, backend)
        if command == "/compact":
            return self._handle_compact(chat, envelope, backend)
        if command == "/restart":
            return self._handle_restart(chat)
        # Unknown command → forward, so the agent (or a later backend) owns it
        # instead of the text silently becoming part of a prompt.
        self._forward(envelope, backend)
        return True

    def _forward(self, envelope: dict, backend) -> None:
        """Send a command envelope straight through — never queued behind a turn."""
        envelope["tg_kind"] = "command"
        reply = backend.dispatch(envelope)
        if reply is not None:            # synchronous backend answers immediately
            self.transport.send(reply)

    def _annotate_restart(self, reply: dict, chat) -> None:
        """Fallback path: append the confirmation to the first reply, and consume it.

        The PRIMARY path is `announce_restarts()` at startup, which tells the chat
        without waiting for it to speak. This runs when that could not happen (the
        send failed, or the marker was written by a process whose successor could
        not reach the chat). Either way the marker is consumed here, after the agent
        has been told the same fact with its prompt.
        """
        if self.restarts is None or not isinstance(reply, dict):
            return
        notice = self.restarts.pending(chat)
        if not notice:
            return
        if not notice.get("announced"):
            body = str(reply.get("body") or "")
            reply["body"] = f"{body}\n\n{RESTART_CONFIRMATION}"
        self.restarts.clear(chat)

    def announce_restarts(self) -> int:
        """Tell every chat that waited on a /restart that the gateway is back.

        Called ONCE at startup, before polling: the restart happened while the only
        process that knew about it was exiting, so a chat has no way to see it —
        earlier today a genuinely restarted gateway (NRestarts=1) left Luke asking
        the agent whether it had restarted, and the agent said no. Returns how many
        chats were told; a failed send leaves the marker so the reply path retries.
        """
        if self.restarts is None:
            return 0
        told = 0
        for chat, _mark in self.restarts.unannounced():
            try:
                self.transport.send({"channel_user_id": _as_chat_id(chat),
                                     "body": RESTART_CONFIRMATION})
            except Exception as e:  # noqa: BLE001 — a notice must never stop startup
                print(f"⚠️  could not announce the restart to chat {chat}: {e} "
                      f"(the next reply there will carry it)", file=sys.stderr)
                continue
            self.restarts.mark_announced(chat)
            told += 1
        if told:
            print(f"♻ announced the restart to {told} chat(s)", file=sys.stderr)
        return told

    def _reply(self, chat, text: str) -> None:
        if chat is None:
            return
        self.transport.send({"channel_user_id": chat, "body": text})

    def _status_line(self) -> str:
        busy = ",".join(str(c) for c in self.inflight) or "none"
        queued = sum(len(q) for q in self.queues.values())
        return (f"gateway ok · backends: {','.join(sorted(self.backends))} · "
                f"in flight: {busy} · queued: {queued}")

    # ── /model: which model answers THIS chat ──────────────────
    def _handle_model(self, chat, envelope: dict, backend) -> bool:
        """Show, switch, or clear this chat's model.

        Handled here rather than forwarded, for the same reason as `/new`: the
        model lives in the argv the BACKEND builds, and the gateway is the only
        component that persists per-chat state. Forwarded, `/model x` is prompt
        prose — pi answers it in words (and keeps running the old model), which is
        exactly the silent no-op this replaces.

        Scope is one chat (the incumbent's session-scoped `/model <name>`): a
        switch here never moves another chat, and a chat that never switches keeps
        running the configured default.
        """
        if self.models is None:
            self._reply(chat, "Model switching is not configured on this gateway — "
                              "this chat uses the backend's default model.")
            return True
        args = (envelope.get("body") or "").split()
        want = " ".join(args[1:]).strip() if len(args) > 1 else ""
        default = str(getattr(getattr(backend, "spec", None), "model", "") or "").strip()
        current = self.models.get(chat)

        if not want or want.lower() in ("status", "show"):
            where = f"this chat: {current}" if current else \
                    f"this chat: {default or '(backend default)'}"
            tail = f" · default: {default}" if current and default else ""
            self._reply(chat, f"🧠 {where}{tail}\n"
                              "/model <name> to switch · /model reset for the default")
            return True
        if want.lower() in ("reset", "default", "clear"):
            had = self.models.clear(chat)
            self._reply(chat, (f"↩️ model reset to the default ({default or 'backend default'})."
                               if had else
                               "This chat was already on the default model."))
            return True

        # Optional validation: a spec may declare a `check_model` command. Without
        # it we accept the name and say so — a typo then surfaces on the next turn
        # (the backend reports a failed turn rather than going silent).
        check = None
        controller = getattr(backend, "control", None)
        if controller is not None and "check_model" in (getattr(backend.spec, "commands", {}) or {}):
            rc, out, err = controller("check_model", envelope, model=want)
            if rc == 1:
                self._reply(chat, f"❌ {want} is not a model this agent can use.\n"
                                  f"{err or out}")
                return True
            if rc == 3:
                check = (" (could not verify it against the agent's model list — "
                         "if the next turn reports a model error, use /model reset)")
            elif out:
                check = f" ({out})"
        self.models.set(chat, want)
        self._reply(chat, f"🧠 model for this chat set to {want}{check or ''}.\n"
                          "Applies from your next message · /model reset restores "
                          f"{default or 'the default'}.")
        return True

    # ── /compact: ask the agent to compact ITS session ─────────
    def _handle_compact(self, chat, envelope: dict, backend) -> bool:
        """Compact this chat's agent-side context.

        Compaction is a session operation, not a message: pi handles `/compact`
        only in its interactive/RPC surfaces, so forwarding the text would just
        add the four characters to the conversation. The backend declares HOW
        (`commands.compact` in gateway.yaml); the gateway only decides WHEN.

        The interim line matters: a real compaction is an LLM call over the whole
        session (measured ~1m46s on a 71-message pi session) and this call blocks
        the turn, so silence for two minutes reads as a hung bot.
        """
        controller = getattr(backend, "control", None)
        if controller is None:
            self._reply(chat, "⚠️ /compact is not supported by this agent backend.")
            return True
        self._reply(chat, "🗜️ compacting this chat's context — this can take a minute…")
        rc, out, err = controller("compact", envelope)
        if rc == 0:
            self._reply(chat, f"🗜️ {out or 'context compacted.'}")
        elif rc == 3:
            self._reply(chat, f"⚠️ /compact could not run: {err or out}")
        elif rc == 2:
            self._reply(chat, "⚠️ /compact is not supported by this agent backend.")
        else:
            self._reply(chat, f"⚠️ /compact: {err or out or 'the agent refused it'}")
        return True

    # ── /restart: bring the gateway back with fresh code ───────
    RESTART_EXIT_DELAY_S = 1.5

    def _own_unit_name(self) -> str:
        """The systemd unit THIS process runs under, from its own cgroup, or "".

        INHERITED-ENV TRAP: systemd exports INVOCATION_ID into the unit's whole
        process tree, so a daemon started by hand from a shell that lives inside
        another service (an agent session, say) sees it too and would believe a
        restart was survivable. The cgroup names the unit we are actually in.
        """
        try:
            cgroup = Path("/proc/self/cgroup").read_text()
        except OSError:
            return ""
        for line in cgroup.splitlines():
            tail = line.rsplit(":", 1)[-1].rstrip("/").rsplit("/", 1)[-1]
            if tail.endswith(".service"):
                return tail
        return ""

    def _supervised_by_systemd(self) -> bool:
        """Will systemd bring THIS process back if it exits?

        Three checks, because each one alone is fooled: the unit env must be
        present, our cgroup must name a unit, and OUR PID must be that unit's
        MainPID (so being a child of someone else's service does not count).
        Anything unverifiable returns False — refusing costs a manual restart,
        while a wrong True silently takes the bot down.
        """
        if not (os.environ.get("INVOCATION_ID") or os.environ.get("JOURNAL_STREAM")):
            return False
        unit = self._own_unit_name()
        if not unit:
            return False
        try:
            done = subprocess.run(["systemctl", "--user", "show", "--property=MainPID",
                                   "--value", unit],
                                  capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0 and done.stdout.strip() == str(os.getpid())

    def _handle_restart(self, chat) -> bool:
        """Restart the gateway so a code/config change goes live.

        Exiting is the mechanism, not `systemctl restart`: the daemon runs under
        `NoNewPrivileges=true`, so it cannot ask systemd to restart it — but it
        does not have to. `Restart=always` brings the unit back on ANY exit, so
        replying first and then exiting is both privilege-free and observable.

        Refusing when unsupervised is deliberate: without systemd, exiting is a
        kill, and a slash command that silently takes the bot down is worse than
        no command at all.

        The reply says what will happen to the CONVERSATION, because "restart" reads
        like "fresh start" and this is not one: sessions survive (that is `/new`).
        Without that, a human reasonably concludes nothing restarted when the next
        answer still remembers everything — measured 2026-10-08, on a restart that
        had genuinely happened.
        """
        if not self._supervised_by_systemd():
            self._reply(chat, "⚠️ This gateway is not running under systemd, so "
                              "/restart cannot bring it back — stop it and start it "
                              "by hand instead.")
            return True
        # Mark BEFORE the reply: the reply is the last thing sent by THIS process,
        # and the marker has to outlive it (it lives in a file, not in memory).
        if self.restarts is not None:
            self.restarts.mark(chat, pid=os.getpid())
        self._reply(chat, "🔄 Restarting the gateway — back in a few seconds.\n"
                          "This conversation continues (send /new for a fresh "
                          "session); I'll confirm as soon as I'm back.")
        threading.Thread(target=self._exit_for_restart, daemon=True).start()
        return True

    def _exit_for_restart(self) -> None:
        """Let the reply land, then exit so systemd restarts the unit."""
        time.sleep(self.RESTART_EXIT_DELAY_S)
        os._exit(0)

    # ── /new: start a fresh session, ARCHIVING the old one ─────
    def _handle_new(self, chat, envelope: dict, backend) -> bool:
        """Rotate this chat's session. The previous conversation is KEPT.

        Handled here rather than forwarded, because the gateway is the only
        component that owns the session id: the agent cannot rotate its own — the
        gateway pins `--session-id` per chat. Forwarded, `/new` is just four
        characters the agent answers as prose (which is what used to happen:
        `pi "/new"` replies "New task. What are we doing?" and keeps all context).

        Archive, not delete (Luke, 2026-10-03). The previous transcript stays on
        disk under its own session id, which is DETERMINISTIC (hc-<agent>-<chat>-g<N>),
        so every archived conversation is findable after the fact. Nothing here
        removes, truncates or renames anything.
        """
        if self.sessions is None:
            self._reply(chat, "Session rotation is not configured on this gateway — "
                              "keep talking to continue this conversation.")
            return True
        # Name the OUTGOING session BEFORE rotating: the envelope still carries the
        # pre-rotation generation, so the backend reports the id we are archiving.
        previous = ""
        namer = getattr(backend, "session_id_for", None)
        if namer is not None:
            try:
                previous = namer(envelope) or ""
            except Exception as e:          # noqa: BLE001 — naming is cosmetic
                print(f"⚠️  could not name the archived session: {e}",
                      file=sys.stderr)
        generation = self.sessions.rotate(chat)
        archived = (f" Previous conversation archived as `{previous}`."
                    if previous else " Previous conversation archived.")
        self._reply(chat, f"🆕 New session (generation {generation}).{archived} "
                          "Your next message starts fresh.")
        return True

    # ── busy / interrupt (G6) ──────────────────────────────────
    # ── typing indicator (parity: "typing…" while a turn runs) ──
    TYPING_REFRESH_S = 4.0        # Telegram shows the action for ~5s

    def _typing(self, chat, envelope=None) -> None:
        """Best-effort: feature-detected, so a transport without typing still works."""
        fn = getattr(self.transport, "send_typing", None)
        if not fn or chat is None:
            return
        try:
            fn(chat, thread_id=(envelope or {}).get("thread_id"))
        except Exception as e:  # noqa: BLE001 — UX must never break a turn
            print(f"⚠️  typing indicator failed: {e}", file=sys.stderr)
        # .get() + mutate the dict we got: the typing keeper thread calls this while the
        # poll loop may be finishing the turn and popping the chat, and an `in`-check
        # followed by item assignment is a real KeyError window between the two threads.
        st = self.inflight.get(chat)
        if st is not None:
            st["typing_ts"] = time.time()

    def _refresh_typing(self) -> None:
        """Keep the indicator alive for every in-flight turn (refreshed, not once)."""
        now = time.time()
        for chat, st in list(self.inflight.items()):
            if now - st.get("typing_ts", 0) >= self.TYPING_REFRESH_S:
                self._typing(chat, st.get("envelope"))

    # ── DM pairing (parity: unknown senders can enrol, with the owner's consent) ──
    def _sender_allowed(self, sender: str) -> bool:
        """Env allowlist ∪ persisted approvals. One place decides who may talk."""
        if self.allowed_users is None:
            return True
        return sender in self.allowed_users or bool(
            self.pairing and self.pairing.is_approved(sender))

    def _is_owner(self, sender: str) -> bool:
        """Only an ENV-allowed user may approve — an approved guest is not an owner."""
        return self.allowed_users is not None and sender in self.allowed_users

    def _notify_owner(self, text: str) -> None:
        """Tell the owner via the home channel (the transport's own fallback)."""
        try:
            self.transport.send({"body": text})
        except Exception as e:  # noqa: BLE001 — a failed notice must not break the loop
            print(f"⚠️  could not notify the owner: {e}", file=sys.stderr)

    def _pair_request(self, envelope: dict, sender: str) -> None:
        """Offer a code and tell the owner. Silent when rate limited (no amplification)."""
        code = self.pairing.request(sender)
        if code is None:
            print(f"⏳ pairing rate limit hit for {sender}", file=sys.stderr)
            return
        self._reply(envelope.get("channel_user_id"),
                    "This bot is not paired with you yet, so your message was not "
                    f"delivered. Ask the owner to approve pairing code {code} "
                    "(it expires shortly).")
        self._notify_owner(
            f"🔐 Pairing request from chat {sender}. Approve with: /approve {code} "
            f"(or /deny {code}). Approving lets that chat talk to the agent.")
        print(f"🔐 pairing requested by {sender} (code issued)", file=sys.stderr)

    def _handle_pair_command(self, command: str, envelope: dict) -> bool:
        """/approve <code> · /deny <code> — owner only."""
        sender = str(envelope.get("channel_user_id"))
        parts = (envelope.get("body") or "").split()
        code = parts[1] if len(parts) > 1 else ""
        if not self._is_owner(sender):
            # An approved guest must not be able to enrol anyone else.
            self._reply(sender, "Only the bot owner can approve or deny pairing requests.")
            return True
        if command == "/deny":
            ok = self.pairing.deny(code)
            self._reply(sender, f"Pairing code {code.upper()} denied." if ok
                        else f"No pending request with code {code.upper()}.")
            return True
        chat = self.pairing.approve(code)
        if chat is None:
            self._reply(sender, f"No valid pending request with code {code.upper()} "
                                "(it may have expired or already been used).")
            return True
        self._reply(sender, f"Approved — chat {chat} can now talk to the agent.")
        try:
            self.transport.send({"channel_user_id": int(chat),
                                 "body": "You are paired. Send your message again and the "
                                         "agent will answer."})
        except Exception as e:  # noqa: BLE001 — approval stands even if the notice fails
            print(f"⚠️  could not notify the newly paired chat: {e}", file=sys.stderr)
        print(f"🔐 paired chat {chat}", file=sys.stderr)
        return True

    def _answer_callback(self, envelope: dict) -> None:
        """Clear a pressed button's spinner. Feature-detected and best-effort."""
        fn = getattr(self.transport, "answer_callback", None)
        if not fn:
            return
        try:
            fn(envelope.get("tg_query_id"))
        except Exception as e:  # noqa: BLE001 — UX must never break a turn
            print(f"⚠️  answering the callback failed: {e}", file=sys.stderr)

    def _interrupt(self, chat) -> int:
        """Forget the in-flight turn and drop what was queued behind it."""
        queued = len(self.queues.pop(chat, []) or [])
        self.inflight.pop(chat, None)
        self.suppressed.add(chat)
        return queued

    def _dispatch_or_queue(self, chat, envelope: dict, backend) -> None:
        """One in-flight turn per chat; arrivals wait their turn (two-level guard)."""
        if chat in self.inflight:
            q = self.queues.setdefault(chat, [])
            if len(q) >= self.max_queue:
                print(f"⚠️  queue full for chat {chat} — dropping oldest",
                      file=sys.stderr)
                q.pop(0)
            q.append(envelope)
            return
        self._start_turn(chat, envelope, backend)

    def _start_turn(self, chat, envelope: dict, backend) -> None:
        """Dispatch one turn. A SYNCHRONOUS backend reply frees the chat at once.

        The hermes backend is async (bus enqueue → None, reply arrives via
        poll_replies), but the seam also allows a backend that returns a reply
        directly — the original daemon sent it, and dropping it here was a
        regression caught by test_cortex_gateway_daemon.py.

        A None reply is ambiguous on its own, so the BACKEND declares which it is
        (`async_replies`). For a synchronous backend None means the turn ENDED with
        nothing to say, and the chat must be freed: leaving it in flight made every
        later message queue behind a turn that could never complete, so the agent
        went permanently silent after one empty turn (measured live with pi).
        """
        self.inflight[chat] = {"ts": time.time(), "envelope": envelope}
        self._typing(chat, envelope)
        streamer = None
        if getattr(backend, "supports_stream", False) and hasattr(self.transport, "edit_message"):
            streamer = _Streamer(self, chat, envelope)
            reply = backend.dispatch(envelope, sink=streamer.partial)
        else:
            reply = backend.dispatch(envelope)
        if reply is not None:
            self._annotate_restart(reply, chat)
            if streamer is not None and streamer.finish(reply.get("body") or ""):
                pass                      # already on screen, updated in place
            else:
                self.transport.send(reply)
            self._next_from_queue(chat)
        elif not _answers_async(backend):
            self._next_from_queue(chat)

    def _next_from_queue(self, chat) -> None:
        """The chat is free → run queued turns until one is async or the queue empties.

        Iterative rather than recursive: a synchronous backend would otherwise
        recurse once per queued message.

        A turn ENDS when a synchronous backend returns (with a reply, or with None
        meaning the agent had nothing to say). It ends LATER only for an async
        backend, whose reply arrives through drain_outbound — so only that case may
        leave the chat in flight.
        """
        self.inflight.pop(chat, None)
        while True:
            q = self.queues.get(chat) or []
            if not q:
                return
            nxt = q.pop(0)
            backend = self.backends.get(nxt.get("to_agent"))
            if backend is None:
                return
            self.inflight[chat] = {"ts": time.time(), "envelope": nxt}
            reply = backend.dispatch(nxt)
            if reply is None and _answers_async(backend):
                return                   # async backend → wait for its reply
            if reply is not None:
                self._annotate_restart(reply, chat)
                self.transport.send(reply)   # sync backend → the chat is free again
            self.inflight.pop(chat, None)

    # ── outbound drain (async replies) ─────────────────────────
    def drain_outbound(self) -> None:
        """poll_replies from every backend → transport.send."""
        for backend in self.backends.values():
            for reply in backend.poll_replies():
                chat = reply.get("channel_user_id")
                if chat in self.suppressed:
                    # /stop dropped this turn: deliver nothing, but free the chat
                    # so the next queued message can run.
                    print(f"🛑 suppressed a reply for chat {chat} (after /stop)",
                          file=sys.stderr)
                    self._next_from_queue(chat)
                    continue
                self._annotate_restart(reply, chat)
                self.transport.send(reply)
                self._next_from_queue(chat)

    # ── polls (G7: recovery) ───────────────────────────────────
    def _poll_delay(self) -> float:
        """Normal cadence when healthy; exponential backoff while polls fail.

        The target used to `return` on any poll error and immediately poll again —
        an error loop that spins a CPU and floods the log — and treated a
        transient conflict as fatal. Backoff bounds both, capped at a minute.
        """
        bad = max(self.consecutive_failures, self.consecutive_conflicts)
        if bad <= 0:
            return DEFAULT_POLL_SECONDS
        return min(60.0, DEFAULT_POLL_SECONDS * (2 ** min(bad, 6)))

    def _note_conflict(self, err) -> None:
        """A second getUpdates consumer. Transient → stand by; persistent → exit.

        Holding the bot lock should make this impossible. If it persists, another
        process genuinely owns the bot and polling on would STEAL its updates —
        so give it a few cycles to clear, then refuse to continue.
        """
        self.consecutive_conflicts += 1
        if self.consecutive_conflicts >= self.max_conflicts:
            print(f"⛔ {self.consecutive_conflicts} consecutive poll conflicts — "
                  "another poller owns this bot", file=sys.stderr)
            raise SystemExit(4)
        print(f"⏸️  poll conflict {self.consecutive_conflicts}/{self.max_conflicts}: "
              f"{err} — standing by {self._poll_delay():.0f}s", file=sys.stderr)

    # ── run loops ──────────────────────────────────────────────
    def run_once(self) -> None:
        self.poll_once()
        self._refresh_typing()
        self.drain_outbound()

    def run_outbound_only(self) -> None:
        """Drain async replies only (another poller owns inbound)."""
        while True:
            self.drain_outbound()
            time.sleep(DEFAULT_POLL_SECONDS)

    def run(self) -> None:
        keeper = _TypingKeeper(self, self.TYPING_REFRESH_S)
        keeper.start()
        while True:
            self.run_once()
            time.sleep(self._poll_delay())

    def run_locked(self) -> None:
        """run() with per-bot advisory locks (no double-poll on cutover)."""
        import bot_locks
        key = bot_locks.bot_key(
            getattr(self.transport, "token_ref",
                    getattr(self.transport, "token", "bot")),
            getattr(self.transport, "channel", "telegram"))
        # The typing keeper is REQUIRED here, not a nicety: a synchronous backend
        # blocks this loop for the whole turn, so nothing else can refresh the
        # indicator. Without it a long CLI-agent turn shows no typing prompt at all.
        keeper = _TypingKeeper(self, self.TYPING_REFRESH_S)
        keeper.start()
        while True:
            with bot_locks.BotLock(bot_locks._connect, key) as acquired:
                if not acquired:
                    print("⏸️  lock held by another gateway — standby",
                          file=sys.stderr)
                else:
                    self.poll_once()
            self._refresh_typing()
            self.drain_outbound()
            time.sleep(self._poll_delay())


# ── config → wiring (env + gateway.yaml) ───────────────────────────────────

def _build_backends(cfg: dict) -> dict:
    """Build BackendAdapters from config through the agent registry (agents.py)."""
    bus_url = cfg.get("bus_url") or os.environ.get("CORTEX_BUS_URL", "")
    bus_token = os.environ.get("CORTEX_BUS_TOKEN", "")
    bus_auth = (cfg.get("bus_auth") or os.environ.get("CORTEX_BUS_AUTH", "")
                or os.environ.get("CORTEX_BASIC_AUTH", ""))
    secret = cfg.get("secret") or os.environ.get("GATEWAY_SECRET", "")
    names = cfg.get("backends", [DEFAULT_BACKEND_AGENT])
    if names and not secret:
        raise SystemExit(
            "cortex-gateway: GATEWAY_SECRET is not set. Every inbound "
            "envelope is HMAC-signed so agents can verify it came from the "
            "gateway; an empty key makes those signatures forgeable by "
            "anyone. Set GATEWAY_SECRET (e.g. `openssl rand -hex 32`) in the "
            "env, or 'secret' in gateway.yaml.")
    headers = _bus_headers(bus_token, bus_auth)
    # The registry validates every entry and fails closed on an unknown kind, so a typo in
    # gateway.yaml is a startup error naming the entry instead of a silent no-backend drop.
    from .agents import build_backends
    return build_backends(cfg.get("backends", [DEFAULT_BACKEND_AGENT]),
                          {"bus_url": bus_url, "bus_headers": headers, "secret": secret})


def _bus_headers(bus_token: str, bus_auth: str) -> dict:
    import base64
    if bus_token:
        return {"Authorization": f"Bearer {bus_token}"}
    return {"Authorization": "Basic "
            + base64.b64encode(bus_auth.encode()).decode()}


def _parse_allowed_users(raw: str) -> set:
    """TELEGRAM_ALLOWED_USERS → a set of chat/user ids (comma or space)."""
    return {tok.strip() for tok in raw.replace(",", " ").split() if tok.strip()}


def build_gateway(config_path: Path) -> Gateway:
    """gateway.yaml + env → a wired Gateway (transport + backends + routing).

    Uses the SAME Telegram env vars Hermes uses — no invented names:
      TELEGRAM_BOT_TOKEN      the bot (via bots[].token_ref)
      TELEGRAM_ALLOWED_USERS  sender allowlist (required, fail-closed)
      TELEGRAM_HOME_CHANNEL   default delivery target (required)
    """
    data = json.loads(config_path.read_text())
    bots = [BotConfig.from_dict(b) for b in data.get("bots", [])]
    if not bots:
        raise SystemExit("gateway.yaml: no bots configured")
    bot = bots[0]
    token = os.environ.get(bot.token_ref, "")
    if not token:
        raise SystemExit(f"gateway.yaml: {bot.token_ref} not set in env")

    allowed = _parse_allowed_users(os.environ.get("TELEGRAM_ALLOWED_USERS", ""))
    if not allowed:
        raise SystemExit(
            "cortex-gateway: TELEGRAM_ALLOWED_USERS is unset or empty — "
            "without an allowlist any Telegram user who finds the bot could "
            "talk to the agent. Set it to the allowed chat/user ids "
            "(comma-separated); this is the same var Hermes uses.")
    home = os.environ.get("TELEGRAM_HOME_CHANNEL", "").strip()
    if not home:
        raise SystemExit(
            "cortex-gateway: TELEGRAM_HOME_CHANNEL is unset — it is the "
            "default delivery target for agent-initiated messages (the same "
            "var Hermes uses).")

    # The poll offset is persisted NEXT TO the deploy and keyed by token_ref, so two
    # gateways on one host never share a resume point (and a deploy never clobbers it).
    _state_dir = Path(os.environ.get(
        "CORTEX_DEPLOY_HOME", str(Path.home() / ".hermes-cortex"))) / "state"
    transport = TelegramAdapter(
        token=token, initial_offset=bot.initial_offset, home_channel=home,
        state_path=_state_dir / f"gateway-offset-{bot.token_ref}.json")
    backends = _build_backends(data)
    routing = data.get("routing", {})
    # Per-chat session generations for `/new`. Persisted NEXT TO the deploy so a
    # rotation survives a restart (the unit comes back after any crash) — an
    # in-memory counter would silently resume the archived conversation.
    from . import sessions as _sessions
    sessions = _sessions.SessionBook(_state_dir / "gateway-sessions.json")
    # Per-chat model overrides for `/model`, persisted for the same reason: the unit
    # is Restart=always, and a switch that evaporates on restart is one a human will
    # (correctly) stop trusting.
    from . import models as _models
    models = _models.ModelBook(_state_dir / "gateway-models.json")
    # Unseen /restart markers, for the confirmation the chat gets once the gateway
    # is back. Persisted for the same reason: the process that marks it exits.
    from . import restarts as _restarts
    restarts = _restarts.RestartBook(_state_dir / "gateway-restarts.json")
    # Pairing is opt-in and its approvals persist NEXT TO the deploy, not in the repo.
    pairing = None
    from . import pairing as _pairing
    if _pairing.enabled():
        store_path = Path(os.environ.get("CORTEX_DEPLOY_HOME", str(Path.home() / ".hermes-cortex"))) / "paired_chats.json"
        pairing = _pairing.PairingStore(store_path)
        print(f"🔐 DM pairing enabled ({len(pairing.approved)} approved chat(s))",
              file=sys.stderr)
    return Gateway(transport=transport, backends=backends,
                   default_agent=routing.get("default", DEFAULT_BACKEND_AGENT),
                   routing_overrides=routing.get("overrides", {}),
                   allowed_users=allowed, pairing=pairing, sessions=sessions,
                   models=models, restarts=restarts)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="cortex-gateway daemon")
    ap.add_argument("--config", default="gateway.yaml")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--outbound-only", action="store_true")
    args = ap.parse_args()
    gw = build_gateway(Path(args.config))
    if args.once:
        gw.run_once()
    elif args.outbound_only:
        gw.run_outbound_only()
    else:
        # Before polling, and only in the serving path: a /restart leaves a marker in
        # a chat that the process which wrote it cannot tell, because it was exiting.
        # This is where the chat finally hears "back, and your session continues".
        gw.announce_restarts()
        gw.run_locked()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
