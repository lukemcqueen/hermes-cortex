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
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
from pathlib import Path

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


class Gateway:
    """The decoupled gateway daemon. Transport ↔ BackendAdapter."""

    def __init__(self, transport: TransportAdapter, backends: dict,
                 default_agent: str = DEFAULT_BACKEND_AGENT,
                 routing_overrides: dict | None = None,
                 allowed_users: set | None = None):
        self.transport = transport
        self.backends = backends          # agent_name -> BackendAdapter
        self.default_agent = default_agent
        self.routing_overrides = routing_overrides or {}
        # Sender allowlist (TELEGRAM_ALLOWED_USERS). None means "not gated
        # here" — build_gateway requires it, so production is never None.
        self.allowed_users = allowed_users
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
            if hasattr(self.transport, "offset"):
                self.transport.offset = self.offset

    def _turn(self, raw: dict) -> None:
        """One app event → parse → route → (command | dispatch) → reply."""
        envelope = self.transport.parse(raw)
        if envelope is None:
            return
        if self.allowed_users is not None:
            sender = str(envelope.get("channel_user_id"))
            if sender not in self.allowed_users:
                print(f"⛔ dropped sender {sender} — not in "
                      "TELEGRAM_ALLOWED_USERS", file=sys.stderr)
                return
        chat = envelope.get("channel_user_id")
        # A new human message lifts a previous /stop suppression.
        if envelope.get("tg_kind") == "message":
            self.suppressed.discard(chat)
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
            self._reply(chat, "gateway commands: /stop · /status · /help — "
                              "anything else is forwarded to the agent")
            return True
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

    def _reply(self, chat, text: str) -> None:
        if chat is None:
            return
        self.transport.send({"channel_user_id": chat, "body": text})

    def _status_line(self) -> str:
        busy = ",".join(str(c) for c in self.inflight) or "none"
        queued = sum(len(q) for q in self.queues.values())
        return (f"gateway ok · backends: {','.join(sorted(self.backends))} · "
                f"in flight: {busy} · queued: {queued}")

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
        if chat in self.inflight:
            self.inflight[chat]["typing_ts"] = time.time()

    def _refresh_typing(self) -> None:
        """Keep the indicator alive for every in-flight turn (refreshed, not once)."""
        now = time.time()
        for chat, st in list(self.inflight.items()):
            if now - st.get("typing_ts", 0) >= self.TYPING_REFRESH_S:
                self._typing(chat, st.get("envelope"))

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
        """
        self.inflight[chat] = {"ts": time.time(), "envelope": envelope}
        self._typing(chat, envelope)
        reply = backend.dispatch(envelope)
        if reply is not None:
            self.transport.send(reply)
            self._next_from_queue(chat)

    def _next_from_queue(self, chat) -> None:
        """The chat is free → run queued turns until one is async or the queue empties.

        Iterative rather than recursive: a synchronous backend would otherwise
        recurse once per queued message.
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
            if reply is None:            # async backend → wait for its reply
                return
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

    transport = TelegramAdapter(token=token, initial_offset=bot.initial_offset,
                                home_channel=home)
    backends = _build_backends(data)
    routing = data.get("routing", {})
    return Gateway(transport=transport, backends=backends,
                   default_agent=routing.get("default", DEFAULT_BACKEND_AGENT),
                   routing_overrides=routing.get("overrides", {}),
                   allowed_users=allowed)


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
        gw.run_locked()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
