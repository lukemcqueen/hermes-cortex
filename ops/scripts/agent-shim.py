#!/usr/bin/env python3
"""agent-shim.py — the standard coding-agent bus shim (ADR-0005).

Coding agents (Codex, Claude Code, Blackbox, Grok...) cannot speak PGMQ
natively. This ONE standard shim gives any coding agent a bus presence:

    poll  inbox_<AGENT>  → the next inbound message (from the gateway:
                           a Telegram/WhatsApp user's message to the agent)
    reply out_<AGENT>    → the agent's answer back (the gateway drains
                           out_<AGENT> and delivers it to the user)
    ack   (archive)      → commit the processed inbound message

QUEUE CONTRACT (fixed 2026-08-24 — live-test review caught the collision):
    inbox_<AGENT>  = messages FOR the agent  (gateway writes, shim reads)
    out_<AGENT>    = messages FROM the agent (shim writes, gateway reads)
    The shim must NEVER read out_<AGENT> — the gateway drains that queue
    to send replies to Telegram; a shim poll would steal replies.

The agent's runtime (Claude Code session, Codex CLI loop, etc.) calls the
shim as a subprocess OR the shim runs as a tiny daemon feeding a local
file/pipe the agent reads. Design (party, Product 8/10): ONE standard
shim, generated per agent (`--generate`), never hand-written bespoke per
agent — expansion must be a config row + a token, not new code.

New coding agent recipe (< 30 min):
    1. cortex-agent-manager.py add codex            # mint scoped token
    2. gateway.yaml: routing row chat → codex       # bot routes to it
    3. agent-shim.py --generate --agent codex       # emit the instance
    4. register the shim's inbox poll in the agent's runtime loop

Usage:
    # as a subprocess from the agent's runtime:
    python3 agent-shim.py --agent codex --poll            # print next msg
    python3 agent-shim.py --agent codex --reply --body 'done' # send reply
    python3 agent-shim.py --agent codex --ack --msg-id m-1    # commit

    # emit a per-agent instance (bakes AGENT_NAME + queue names):
    python3 agent-shim.py --generate --agent codex > codex-shim.py

Bus creds from env: CORTEX_BUS_URL + CORTEX_BUS_TOKEN (or CORTEX_BUS_AUTH).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# Functional URLs come from env, never source (env-first rule).
_BUS_URL = os.environ.get("CORTEX_BUS_URL", "").strip()


def _headers() -> dict:
    token = os.environ.get("CORTEX_BUS_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    auth = (os.environ.get("CORTEX_BUS_AUTH", "")
            or os.environ.get("CORTEX_BASIC_AUTH", "")).strip()
    if auth:
        import base64
        return {"Authorization": "Basic "
                + base64.b64encode(auth.encode()).decode()}
    return {}


def _post(path: str, payload: dict) -> Optional[dict]:
    if not _BUS_URL:
        raise RuntimeError("CORTEX_BUS_URL not set")
    req = urllib.request.Request(f"{_BUS_URL}{path}",
                                 data=json.dumps(payload).encode(),
                                 method="POST")
    for k, v in _headers().items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError:
        return None


def poll_inbox(bus_url: str, headers: dict, agent: str,
               vt: int = 60) -> Optional[dict]:
    """Read (dequeue) the next inbound message from inbox_<AGENT>.

    inbox_<AGENT> = messages FOR the agent (the gateway writes Telegram/
    WhatsApp user messages here). The shim reads this to feed the agent.
    """
    payload = json.dumps({"queue": f"inbox_{agent}", "vt": vt}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/read", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError:
        return None


def reply(bus_url: str, headers: dict, agent: str, body: dict) -> bool:
    """Send the agent's answer to out_<AGENT> (gateway drains → Telegram)."""
    return _send(bus_url, headers, f"out_{agent}", body)


def _send(bus_url: str, headers: dict, queue: str, body: dict) -> bool:
    payload = json.dumps({"queue": queue, "message": body}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/send", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


def ack(bus_url: str, headers: dict, agent: str, msg_id: str) -> bool:
    """Archive (commit) a processed inbox_<AGENT> message.

    The shim polls inbox_<AGENT>; after the agent handles the message,
    ack archives it (commit point — PGMQ redelivers un-archived messages
    on visibility timeout, so ack-after-handle gives at-least-once).
    """
    payload = json.dumps({"queue": f"inbox_{agent}", "msg_id": msg_id}).encode()
    req = urllib.request.Request(f"{bus_url}/api/pgmq/archive", data=payload,
                                 method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 201)
    except urllib.error.URLError:
        return False


def generate(out_path: Path, agent: str) -> None:
    """Emit a per-agent shim instance (bakes AGENT_NAME + queue names)."""
    template = f'''#!/usr/bin/env python3
"""Codex/Claude Code bus shim for agent '{agent}' (generated).

Speaks the ADR-0005 envelope contract against the Agent Bus:
    poll  inbox_{agent}  → next inbound message (Telegram/WhatsApp user)
    reply out_{agent}    → answer back (gateway delivers to the user)
Requires CORTEX_BUS_URL + CORTEX_BUS_TOKEN (or CORTEX_BUS_AUTH) in env.
"""
import json
import os
import sys
import urllib.error
import urllib.request

AGENT = "{agent}"


def _post(path, payload):
    url = os.environ.get("CORTEX_BUS_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("CORTEX_BUS_URL not set")
    req = urllib.request.Request(url + path,
                                 data=json.dumps(payload).encode(),
                                 method="POST")
    tok = os.environ.get("CORTEX_BUS_TOKEN", "").strip()
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    else:
        import base64
        auth = (os.environ.get("CORTEX_BUS_AUTH", "")
                or os.environ.get("CORTEX_BASIC_AUTH", "")).strip()
        if auth:
            req.add_header("Authorization", "Basic "
                           + base64.b64encode(auth.encode()).decode())
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if action == "poll":
        msg = _post("/api/pgmq/read", {{"queue": "inbox_{agent}", "vt": 60}})
        if msg and msg.get("msg_id"):
            print(json.dumps(msg))
        return
    if action == "ack":
        mid = sys.argv[2]
        _post("/api/pgmq/archive", {{"queue": "inbox_{agent}", "msg_id": mid}})
        return
    if action == "reply":
        body = sys.argv[2] if len(sys.argv) > 2 else ""
        _post("/api/pgmq/send",
              {{"queue": "out_{agent}", "message": {{"text": body}}}})
        return
    raise SystemExit(f"unknown action: {{action}}")


if __name__ == "__main__":
    main()
'''
    out_path.write_text(template)
    os.chmod(out_path, 0o755)


# ── CLI ──────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Coding-agent bus shim")
    ap.add_argument("--agent", default=os.environ.get("AGENT_NAME", ""))
    ap.add_argument("--generate", action="store_true",
                    help="emit a per-agent shim instance to stdout")
    ap.add_argument("--poll", action="store_true",
                    help="print the next out_<AGENT> message")
    ap.add_argument("--reply", action="store_true")
    ap.add_argument("--body", default="")
    ap.add_argument("--ack", action="store_true")
    ap.add_argument("--msg-id", default="")
    args = ap.parse_args()

    if not args.agent:
        print("error: --agent required (or AGENT_NAME env)", file=sys.stderr)
        return 2

    if args.generate:
        generate(Path("/dev/stdout"), args.agent)
        return 0

    bus_url = os.environ.get("CORTEX_BUS_URL", "").strip()
    if not bus_url:
        print("error: CORTEX_BUS_URL not set", file=sys.stderr)
        return 2
    headers = _headers()

    if args.poll:
        msg = poll_inbox(bus_url, headers, args.agent)
        if msg and msg.get("msg_id"):
            print(json.dumps(msg))
        return 0
    if args.reply:
        return 0 if reply(bus_url, headers, args.agent, {"text": args.body}) else 1
    if args.ack:
        if not args.msg_id:
            print("error: --msg-id required for --ack", file=sys.stderr)
            return 2
        return 0 if ack(bus_url, headers, args.agent, args.msg_id) else 1

    print("error: one of --poll/--reply/--ack/--generate required",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
