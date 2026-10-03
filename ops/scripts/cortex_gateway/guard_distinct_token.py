#!/usr/bin/env python3
"""Refuse to start a gateway that would poll the LIVE bot's token.

Both gateway units read the SAME canonical env (`~/hermes-cortex/.env`). What
separates them is only the ``token_ref`` in their config:

    gateway.yaml                token_ref: TELEGRAM_BOT_TOKEN    <- the LIVE bot
    gateway-esther0001.yaml     token_ref: ESTHER0001_BOT_TOKEN  <- the second bot

``TELEGRAM_BOT_TOKEN`` is byte-identical to ``~/.hermes/.env`` — the bot
``hermes-gateway.service`` is already polling. A second poller on one bot token
gets a Telegram **409 Conflict**, and the casualty is whichever poller Telegram
drops: the LIVE channel.

That separation used to live only in a comment at the top of the unit file. **A
comment is not a guard — it cannot fail, and it never runs.** This runs as
``ExecStartPre``, so systemd REFUSES to start the unit instead of breaking the
live channel.

Usage::

    guard_distinct_token.py <config.yaml>

Exit codes: 0 = distinct (safe to start), 1 = same token as the live bot (refuse).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

LIVE_TOKEN_REF = "TELEGRAM_BOT_TOKEN"


def _fingerprint(secret: str) -> str:
    """Short hash — enough to compare and to name in a message, never the value."""
    return hashlib.sha256(secret.encode()).hexdigest()[:12]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("guard: usage: guard_distinct_token.py <config.yaml>", file=sys.stderr)
        return 1

    config_path = Path(argv[1])
    try:
        data = json.loads(config_path.read_text())
    except (OSError, ValueError) as e:
        print(f"guard: cannot read config {config_path}: {e}", file=sys.stderr)
        return 1

    bots = data.get("bots") or []
    if not bots:
        print(f"guard: {config_path} configures no bots", file=sys.stderr)
        return 1
    token_ref = str((bots[0] or {}).get("token_ref") or "")
    if not token_ref:
        print(f"guard: {config_path} bot has no token_ref", file=sys.stderr)
        return 1

    # Naming the live var IS the production config, whatever it currently holds.
    # Refuse on the name as well as the value: a rotated live token must not turn
    # a dangerous config into an accepted one.
    if token_ref == LIVE_TOKEN_REF:
        print(
            f"guard: REFUSING TO START — token_ref is {LIVE_TOKEN_REF}, the LIVE bot.\n"
            "  This unit exists to run a SECOND bot. Point it at a distinct token "
            "(see gateway-esther0001.yaml).",
            file=sys.stderr)
        return 1

    mine = os.environ.get(token_ref, "")
    if not mine:
        print(f"guard: {token_ref} is not set in the environment — the gateway "
              "cannot start without its token", file=sys.stderr)
        return 1

    live = os.environ.get(LIVE_TOKEN_REF, "")
    if live and mine == live:
        print(
            "guard: REFUSING TO START — this config resolves to the LIVE bot's token.\n"
            f"  config token_ref  : {token_ref}\n"
            f"  token fingerprint : {_fingerprint(mine)}\n"
            f"  {LIVE_TOKEN_REF}  : {_fingerprint(live)}  "
            "(the bot hermes-gateway.service polls)\n"
            "  A second poller on one bot token gets a Telegram 409 and the live "
            "channel is the casualty. Point this unit at a DISTINCT bot token, or "
            "stop hermes-gateway.service first.",
            file=sys.stderr)
        return 1

    print(f"guard: ok — {token_ref} ({_fingerprint(mine)}) is distinct from "
          f"{LIVE_TOKEN_REF}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
