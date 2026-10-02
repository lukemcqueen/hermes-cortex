#!/usr/bin/env python3
"""agent-reply — the generic agent-side reply primitive.

Any agent that can run a command can answer the human: hand it the ORIGIN envelope (the
inbound message it was asked about) and the text it wants to say, and this publishes the
reply to ``out_<agent>`` for the gateway to drain.

    agent-reply --origin-file inbound.json --text "the answer"
    echo "the answer" | agent-reply --origin-file inbound.json
    agent-reply --channel telegram --chat 12345 --text "proactive note"

Why this shape (2026-10-02, "generic interfaces so we can add new coding agents easily"):
the queue contract is the same for every agent, so it lives in ONE place — CLI agents
(pi, codex, claude, opencode, a bespoke script), the bus MCP, and the shim all use this or
the function it wraps. Nothing about a particular agent enters the gateway.

The one rule: ROUTING COMES FROM THE ORIGIN ENVELOPE. The agent supplies text; where the
message goes is decided by the gateway that saw the human.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import gateway_envelope as env                                  # noqa: E402
from cortex_gateway.agents import publish_reply, reply_from_origin   # noqa: E402


def _agent_name(explicit: str = "") -> str:
    name = (explicit or os.environ.get("AGENT_NAME", "") or "").strip()
    if not name:
        raise SystemExit(
            "agent-reply: no agent name. Pass --agent or set AGENT_NAME — the reply queue "
            "is out_<agent>, so guessing it would send the answer to the wrong inbox.")
    return name


def _bus_config() -> tuple:
    """(bus_url, headers) from the cortex env — the same source every other client uses."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
    import lib.cortex_bus as cb  # noqa: PLC0415
    auth = {}
    if cb.CORTEX_BUS_TOKEN:
        auth = {"Authorization": f"Bearer {cb.CORTEX_BUS_TOKEN}"}
    elif cb.CORTEX_BUS_AUTH:
        import base64
        auth = {"Authorization": "Basic " + base64.b64encode(cb.CORTEX_BUS_AUTH.encode()).decode()}
    return cb.BUS_URL, auth


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send an agent's reply to the gateway")
    ap.add_argument("--agent", default="", help="agent name (default: $AGENT_NAME)")
    ap.add_argument("--origin-file", default="", help="JSON file holding the ORIGIN envelope")
    ap.add_argument("--origin-json", default="", help="the ORIGIN envelope as a JSON string")
    ap.add_argument("--channel", default="", help="explicit routing (proactive message)")
    ap.add_argument("--chat", default="", help="explicit chat id (proactive message)")
    ap.add_argument("--thread-id", default="")
    ap.add_argument("--text", default="", help="the reply text (default: stdin)")
    args = ap.parse_args(argv)

    agent = _agent_name(args.agent)
    # `args.text or sys.stdin.read()` misses a whitespace-only --text: "   " is a TRUTHY
    # string, so it skipped the empty check and travelled all the way into the envelope
    # validator ("channel '' not in [...]") — a stray error instead of the intended refusal.
    # Found by tests/test_agent_reply_cli.py::test_refuses_empty_text_no_origin_and_no_agent.
    text = (args.text if args.text else sys.stdin.read()).strip()
    if not text:
        raise SystemExit("agent-reply: refusing to send an empty reply")

    if args.origin_file:
        origin = json.loads(Path(args.origin_file).read_text())
    elif args.origin_json:
        origin = json.loads(args.origin_json)
    elif args.channel and args.chat:
        # A proactive message has no origin: the caller states the routing explicitly.
        # The envelope requires an INT chat id (a Telegram id is numeric) — coercing here
        # with a clear message beats an EnvelopeError from deep inside validate().
        try:
            chat_id = int(str(args.chat).strip())
        except ValueError:
            raise SystemExit(f"agent-reply: --chat must be a numeric chat id, got {args.chat!r}")
        thread_id = None
        if args.thread_id:
            try:
                thread_id = int(str(args.thread_id).strip())
            except ValueError:
                raise SystemExit(f"agent-reply: --thread-id must be numeric, got {args.thread_id!r}")
        origin = {"channel": args.channel, "channel_user_id": chat_id, "thread_id": thread_id}
    else:
        raise SystemExit(
            "agent-reply: need an origin (--origin-file/--origin-json) so the reply goes back "
            "where the message came from, or explicit --channel + --chat for a proactive send.")

    try:
        reply = reply_from_origin(origin, text, agent=agent)
    except ValueError as e:
        raise SystemExit(f"agent-reply: {e}")

    bus_url, headers = _bus_config()
    if not bus_url:
        raise SystemExit("agent-reply: CORTEX_BUS_URL is not configured (checked the cortex env)")

    ok = publish_reply(bus_url, headers, agent, reply)
    if not ok:
        print(
            f"agent-reply: FAILED to publish to out_{agent} — the reply was NOT delivered.\n"
            f"  Check the bus URL, and that {agent} has write access to out_{agent} "
            f"(bus.permissions).", file=sys.stderr)
        return 1
    print(json.dumps({"queued_for": f"out_{agent}", "msg_id": reply["msg_id"],
                      "channel": reply["channel"], "chat": reply["channel_user_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
