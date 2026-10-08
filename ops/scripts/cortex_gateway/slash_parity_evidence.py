#!/usr/bin/env python3
"""slash_parity_evidence.py — re-runnable acceptance check for the gateway's
slash commands against a LIVE agent, on the DEPLOYED tree.

WHAT IT PROVES, and what it deliberately does not. Every command here is driven
through the real `Gateway` (the deployed package) with the real `CommandBackend`
spawned from the live `gateway.yaml` spec — so a pi turn is a real pi process and
a real model call. Only the TRANSPORT is stubbed: a script cannot be the systemd
unit's main process, so it must not poll the bot token (a second poller 409s the
live channel). The Telegram leg is proven separately by the reply-path evidence.

Run it ON the host, from anywhere:

    python3 ~/.hermes-cortex/scripts/cortex_gateway/slash_parity_evidence.py \
        [--config ~/.hermes-cortex/gateway-esther0001.yaml] [--chat 999001] \
        [--model openrouter/moonshotai/kimi-k2.6] [--no-llm]

`--no-llm` skips the turns that call a model (the /model, /new and /restart legs
need no model at all); the full run costs a few cents.

Exit: 0 all checks passed · 1 a check failed · 3 could not verify (no config/agent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_gateway(config: Path, chat, tmp: Path):
    """The deployed Gateway wired from the live config, with THROWAWAY state."""
    sys.path.insert(0, str(HERE.parent))
    import cortex_gateway.agents as agents
    import cortex_gateway.daemon as daemon
    import cortex_gateway.models as models
    import cortex_gateway.sessions as sessions

    cfg = json.loads(Path(config).expanduser().read_text())
    specs = cfg.get("backends") or []
    if not specs:
        print("no backends in the config", file=sys.stderr)
        raise SystemExit(3)
    secret = os.environ.get("GATEWAY_SECRET", "")
    if not secret:
        print("GATEWAY_SECRET is unset — source the cortex env first "
              "(~/hermes-cortex/.env)", file=sys.stderr)
        raise SystemExit(3)
    backends = agents.build_backends(
        specs, {"bus_url": "", "bus_headers": {}, "secret": secret})

    class StubTransport:
        """Records what the gateway would have sent. Never polls."""

        offset = 0

        def __init__(self):
            self.sent: list = []

        def parse(self, raw):
            return dict(raw)

        def send(self, envelope):
            self.sent.append(envelope)
            body = str(envelope.get("body", ""))
            print(f"   ⤶ {body[:400]}{'…' if len(body) > 400 else ''}")
            return True

    transport = StubTransport()
    gw = daemon.Gateway(
        transport=transport, backends=backends,
        default_agent=(cfg.get("routing") or {}).get("default", "pi"),
        routing_overrides=(cfg.get("routing") or {}).get("overrides", {}),
        allowed_users=None,
        sessions=sessions.SessionBook(tmp / "sessions.json"),
        models=models.ModelBook(tmp / "models.json"),
    )
    return gw, transport, backends, cfg


_checks: list = []


def check(label: str, ok: bool, detail: str = "") -> None:
    _checks.append((label, ok))
    print(f"   {'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")


def turn(gw, body, chat) -> list:
    """One human message, shaped exactly as the real transport shapes it.

    Returns the replies produced by THIS turn only — a check that inspects
    `sent[-1]` instead passes vacuously when a turn produces nothing at all
    (measured: a string chat id made every agent turn DLQ silently, and the
    "the agent answered" check still passed on the PREVIOUS reply).
    """
    import uuid
    before = len(gw.transport.sent)
    print(f"  ↳ {body[:200]}")
    gw._turn({
        "msg_id": str(uuid.uuid4()), "ts": 1, "to_agent": "pi", "channel": "telegram",
        "channel_user_id": chat, "thread_id": None, "body": body, "media": [],
        "reply_to_msg_id": None, "ack_required": False, "tg_kind": "message",
    })
    return gw.transport.sent[before:]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Acceptance check for the gateway's slash commands against a "
                    "live agent, on the deployed tree")
    ap.add_argument("--config", default=str(Path.home() / ".hermes-cortex" /
                                            "gateway-esther0001.yaml"))
    ap.add_argument("--chat", default="999001")
    ap.add_argument("--model", default="")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the turns that call a model")
    args = ap.parse_args()

    config = Path(args.config).expanduser()
    if not config.is_file():
        print(f"no such config: {config}", file=sys.stderr)
        return 3
    # INT, like the real transport produces: `channel_user_id` is validated as an
    # int by the envelope, and a string chat id is DLQ'd before the agent ever runs
    # (the gateway then correctly sends nothing — a trap this script must not fall
    # into, or every "the agent answered" check passes vacuously).
    chat = int(args.chat)

    with tempfile.TemporaryDirectory(prefix="slash-parity-") as td:
        tmp = Path(td)
        gw, transport, backends, cfg = _load_gateway(config, chat, tmp)
        spec = next(iter(backends.values())).spec
        default_model = args.model or spec.model
        print(f"backend: {spec.name} · default model: {default_model} · "
              f"declared commands: {sorted(spec.commands)}")

        print("\n[1] /help and /status are answered by the gateway, not the agent")
        replies = turn(gw, "/help", chat)
        check("help lists the gateway commands",
              any("/model" in str(r.get("body", "")) for r in replies))
        replies = turn(gw, "/status", chat)
        check("status is a gateway line",
              any(str(r.get("body", "")).startswith("gateway ok") for r in replies))

        print("\n[2] /model — switch, report, validate, reset (no model call)")
        replies = turn(gw, f"/model {default_model}", chat)
        check("a valid model is accepted",
              any("set to" in str(r.get("body", "")) for r in replies))
        replies = turn(gw, "/model", chat)
        check("bare /model reports this chat's model",
              any(default_model in str(r.get("body", "")) for r in replies))
        replies = turn(gw, "/model definitely/not-a-real-model-xyz", chat)
        rejected = any("not a model" in str(r.get("body", "")) for r in replies)
        if "check_model" in spec.commands:
            check("an unknown model is refused by the agent's own check", rejected)
        else:
            check("no check_model declared — a name is accepted with a note",
                  any("could not verify" in str(r.get("body", "")) for r in replies))
        replies = turn(gw, "/model reset", chat)
        check("reset returns to the default",
              any("reset" in str(r.get("body", "")).lower() for r in replies))

        print("\n[3] /new — fresh session id, previous one NAMED and kept")
        replies = turn(gw, "/new", chat)
        body = " ".join(str(r.get("body", "")) for r in replies)
        check("a new generation is announced", "New session" in body, body[:160])
        check("the archived session is named", f"hc-{spec.name}-{chat}" in body)
        archived = Path(os.path.expanduser("~/.pi/agent/sessions"))
        check("transcripts live on disk (archive, not delete)",
              (not archived.exists()) or any(archived.rglob("*.jsonl")))

        if not args.no_llm:
            print(f"\n[4] a real turn through the live agent ({spec.name})")
            replies = turn(gw, "Reply with exactly: PONG", chat)
            reply = " ".join(str(r.get("body", "")) for r in replies)
            check("the agent answered (a reply arrived for THIS turn)",
                  "PONG" in reply.upper(), reply[:200] or "(no reply at all)")

            print("\n[5] /compact against the LIVE session (a real compaction)")
            if "compact" in spec.commands:
                replies = turn(gw, "/compact", chat)
                bodies = [str(r.get("body", "")) for r in replies]
                check("compaction ran, or said why it could not",
                      any("compacted" in b or "too small" in b for b in bodies),
                      " | ".join(b[:120] for b in bodies))
            else:
                check("no compact command declared — the gateway says so", False,
                      "declare commands.compact in gateway.yaml")
        else:
            print("\n[4]/[5] skipped (--no-llm)")

        print("\n[6] /restart supervision check (this script is NOT the unit's main process)")
        supervised = gw._supervised_by_systemd()
        replies = turn(gw, "/restart", chat)
        body = " ".join(str(r.get("body", "")) for r in replies)
        if supervised:
            check("supervised → restart announced", "restarting" in body, body[:120])
        else:
            check("NOT the unit's main process → refuses and names the reason",
                  "not running under systemd" in body, body[:160])

        print("\n[7] an unknown command still belongs to the agent")
        replies = turn(gw, "/totally-unknown-command", chat)
        check("forwarded — the agent's own answer came back for THIS turn",
              any(str(r.get("body", "")).strip() for r in replies),
              "(no reply: forwarded but the agent said nothing?)")

    failed = [label for label, ok in _checks if not ok]
    print("\n" + "=" * 62)
    print(f"{len(_checks) - len(failed)}/{len(_checks)} checks passed")
    for label in failed:
        print(f"  FAILED: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
