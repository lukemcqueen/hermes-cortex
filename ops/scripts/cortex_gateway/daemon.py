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

from .transport import (DEFAULT_POLL_SECONDS, BotConfig, TransportAdapter,
                        TelegramAdapter)

DEFAULT_BACKEND_AGENT = "hermes"


class Gateway:
    """The decoupled gateway daemon. Transport ↔ BackendAdapter."""

    def __init__(self, transport: TransportAdapter, backends: dict,
                 default_agent: str = DEFAULT_BACKEND_AGENT,
                 routing_overrides: dict | None = None):
        self.transport = transport
        self.backends = backends          # agent_name -> BackendAdapter
        self.default_agent = default_agent
        self.routing_overrides = routing_overrides or {}
        # offset tracks the transport's own offset (transport owns the truth).
        self.offset = getattr(transport, "offset", 0)

    # ── routing ────────────────────────────────────────────────
    def route(self, chat_id) -> str:
        if chat_id is not None and str(chat_id) in self.routing_overrides:
            return str(self.routing_overrides[str(chat_id)])
        return self.default_agent

    # ── one inbound poll cycle ─────────────────────────────────
    def poll_once(self) -> None:
        """getUpdates → parse → route → dispatch → sync reply → send."""
        try:
            updates = self.transport.get_updates(timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                print("⛔ 409: ANOTHER poller owns this bot (lock should "
                      "prevent this)", file=sys.stderr)
                raise SystemExit(4)
            print(f"⚠️  getUpdates HTTP {e.code}", file=sys.stderr)
            return
        except Exception as e:
            print(f"⚠️  poll error: {e}", file=sys.stderr)
            return

        for upd in updates:
            uid = upd.get("update_id")
            if uid is None:
                continue
            self._turn(upd)
            self.offset = max(self.offset, uid + 1)
            if hasattr(self.transport, "offset"):
                self.transport.offset = self.offset

    def _turn(self, raw: dict) -> None:
        """One app event → parse → route → dispatch → sync reply → send."""
        envelope = self.transport.parse(raw)
        if envelope is None:
            return
        envelope["to_agent"] = self.route(envelope["channel_user_id"])
        backend = self.backends.get(envelope["to_agent"])
        if backend is None:
            print(f"⚠️  no backend for agent {envelope['to_agent']}",
                  file=sys.stderr)
            return
        reply = backend.dispatch(envelope)
        if reply is not None:
            self.transport.send(reply)

    # ── outbound drain (async replies) ─────────────────────────
    def drain_outbound(self) -> None:
        """poll_replies from every backend → transport.send."""
        for backend in self.backends.values():
            for reply in backend.poll_replies():
                self.transport.send(reply)

    # ── run loops ──────────────────────────────────────────────
    def run_once(self) -> None:
        self.poll_once()
        self.drain_outbound()

    def run_outbound_only(self) -> None:
        """Drain async replies only (another poller owns inbound)."""
        while True:
            self.drain_outbound()
            time.sleep(DEFAULT_POLL_SECONDS)

    def run(self) -> None:
        while True:
            self.run_once()
            time.sleep(DEFAULT_POLL_SECONDS)

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
            self.drain_outbound()
            time.sleep(DEFAULT_POLL_SECONDS)


# ── config → wiring (env + gateway.yaml) ───────────────────────────────────

def _build_backends(cfg: dict) -> dict:
    """Build BackendAdapters from config. hermes is the default reference."""
    from .hermes_backend import HermesBackend
    bus_url = cfg.get("bus_url") or os.environ.get("CORTEX_BUS_URL", "")
    bus_token = os.environ.get("CORTEX_BUS_TOKEN", "")
    bus_auth = (cfg.get("bus_auth") or os.environ.get("CORTEX_BUS_AUTH", "")
                or os.environ.get("CORTEX_BASIC_AUTH", ""))
    secret = cfg.get("secret") or os.environ.get("GATEWAY_SECRET", "")
    headers = _bus_headers(bus_token, bus_auth)
    backends = {}
    for name in cfg.get("backends", [DEFAULT_BACKEND_AGENT]):
        backends[name] = HermesBackend(agent=name, bus_url=bus_url,
                                       bus_headers=headers, secret=secret)
    return backends


def _bus_headers(bus_token: str, bus_auth: str) -> dict:
    import base64
    if bus_token:
        return {"Authorization": f"Bearer {bus_token}"}
    return {"Authorization": "Basic "
            + base64.b64encode(bus_auth.encode()).decode()}


def build_gateway(config_path: Path) -> Gateway:
    """gateway.yaml → a wired Gateway (transport + backends + routing)."""
    data = json.loads(config_path.read_text())
    bots = [BotConfig.from_dict(b) for b in data.get("bots", [])]
    if not bots:
        raise SystemExit("gateway.yaml: no bots configured")
    bot = bots[0]
    token = os.environ.get(bot.token_ref, "")
    if not token:
        raise SystemExit(f"gateway.yaml: {bot.token_ref} not set in env")
    transport = TelegramAdapter(token=token, initial_offset=bot.initial_offset)
    backends = _build_backends(data)
    routing = data.get("routing", {})
    return Gateway(transport=transport, backends=backends,
                   default_agent=routing.get("default", DEFAULT_BACKEND_AGENT),
                   routing_overrides=routing.get("overrides", {}))


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
