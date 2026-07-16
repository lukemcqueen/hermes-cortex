#!/usr/bin/env python3
"""bus-forwarder.py — Bidirectional bus sync for primary/backup failover.

ARCHITECTURE
  Two bus instances (Moses primary, Esther backup). Each runs this forwarder.
  On every tick, BOTH directions are attempted:
    1. Pull from PEER → push to LOCAL  (backup stays warm)
    2. Pull from LOCAL → push to PEER  (backlog drain on recovery)

  Seen msg_ids are tracked per-direction so each message is forwarded exactly
  once, preventing loops. If one bus is unreachable, that direction silently
  fails; when it returns, accumulated messages drain on the next tick.

FAILOVER SCENARIO
  Normal:      Moses primary → forwarder copies to Esther (warm standby)
  Moses down:  agents use Esther's bus. Forwarder fails silently on the
               Moses→Esther direction. Esther accumulates messages.
  Moses back:  forwarder detects peer is reachable. The LOCAL→PEER direction
               drains Esther's backlog to Moses. Next tick, normal sync resumes.

USAGE
  Configured per-instance via env vars or the section at the bottom.
  Run as a no_agent cron: */2 * * * *

  Output (no_agent pattern):
    Empty   → silent (nothing new to sync)
    Text    → delivered (messages synced)
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "bus-forwarder-state.json"
TIMEOUT = 15
MAX_PER_QUEUE = 10  # max messages to read per queue per tick

# ── Instance config — override via env vars or edit below ──────────
# On Esther: peer=Moses (external), local=self (127.0.0.1:8905)
# On Moses:  peer=Esther (external), local=self (127.0.0.1:8905)

PEER_URL = os.environ.get("BUS_FORWARDER_PEER_URL", "https://bus.example.org:13004")
PEER_AUTH = os.environ.get("BUS_FORWARDER_PEER_AUTH", "esther:d01931493c7a4f7d")
LOCAL_URL = os.environ.get("BUS_FORWARDER_LOCAL_URL", "http://127.0.0.1:8905")
LOCAL_TOKEN = os.environ.get("BUS_FORWARDER_LOCAL_TOKEN", "hbus_d2739edfda4885356707e97cb8e39e730c721c26f258ce91e190b2254d80e35b")

# All agent inbox queues
QUEUES = ["inbox_moses", "inbox_esther", "inbox_joseph", "inbox_titus", "inbox_gisu", "inbox_kustos"]


def _read_bus(url: str, auth: str, token: str, queue: str) -> dict | None:
    """Read (dequeue) one message from a bus. Returns None if queue empty."""
    headers = {"Content-Type": "application/json"}
    payload = json.dumps({"queue": queue, "vt": 0}).encode()

    # Use Bearer token if available, else Basic auth
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        encoded = base64.b64encode(auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    req = urllib.request.Request(
        f"{url}/api/pgmq/read",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data if data.get("msg_id") else None
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _send_bus(url: str, auth: str, token: str, queue: str, body: dict | str) -> bool:
    """Send a message to a bus. Returns True on success."""
    headers = {"Content-Type": "application/json"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass
    payload = json.dumps({"queue": queue, "message": body}).encode()

    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        encoded = base64.b64encode(auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    req = urllib.request.Request(
        f"{url}/api/pgmq/send",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
        return False


def _sync_direction(
    state: dict,
    source_url: str,
    source_auth: str,
    source_token: str,
    dest_url: str,
    dest_auth: str,
    dest_token: str,
    direction: str,
) -> tuple[list[str], list[str]]:
    """Sync messages from source bus to destination bus.

    Returns (forwarded_ids, error_ids) for this direction.
    """
    seen_key = f"seen_{direction}"
    total_key = f"total_{direction}"
    seen = set(state.get(seen_key, []))
    total = state.get(total_key, 0)
    forwarded: list[str] = []
    errors: list[str] = []

    for queue in QUEUES:
        for _ in range(MAX_PER_QUEUE):
            msg = _read_bus(source_url, source_auth, source_token, queue)
            if msg is None:
                break
            msg_id = msg["msg_id"]
            if msg_id in seen:
                continue
            body = msg.get("body", {})
            if _send_bus(dest_url, dest_auth, dest_token, queue, body):
                seen.add(msg_id)
                forwarded.append(f"{queue}/{msg_id[:8]}")
                total += 1
            else:
                errors.append(f"{queue}/{msg_id[:8]}")
                break  # destination unreachable — stop this queue

    state[seen_key] = list(seen)
    state[total_key] = total
    return forwarded, errors


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    state.setdefault("total_peer_to_local", 0)
    state.setdefault("total_local_to_peer", 0)
    state.setdefault("seen_peer_to_local", [])
    state.setdefault("seen_local_to_peer", [])

    # ── Direction 1: PEER → LOCAL (warm standby sync) ──────────
    p2l_fwd, p2l_err = _sync_direction(
        state,
        PEER_URL, PEER_AUTH, "",         # source = peer, Basic auth
        LOCAL_URL, "", LOCAL_TOKEN,       # dest = local, Bearer token
        "peer_to_local",
    )

    # ── Direction 2: LOCAL → PEER (backlog drain on recovery) ──
    l2p_fwd, l2p_err = _sync_direction(
        state,
        LOCAL_URL, "", LOCAL_TOKEN,       # source = local, Bearer token
        PEER_URL, PEER_AUTH, "",          # dest = peer, Basic auth
        "local_to_peer",
    )

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

    # ── Output (no_agent: empty = silent — only alert on errors) ─
    output = []
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if p2l_err:
        output.append(f"⚠️  [{now}] PEER→LOCAL: {len(p2l_err)} message(s) failed — peer unreachable?")
        for f in p2l_err[:3]:
            output.append(f"  • {f}")
        if len(p2l_err) > 3:
            output.append(f"  … +{len(p2l_err)-3} more")
    if l2p_err:
        output.append(f"⚠️  [{now}] LOCAL→PEER: {len(l2p_err)} message(s) failed — peer unreachable?")
        for f in l2p_err[:3]:
            output.append(f"  • {f}")
        if len(l2p_err) > 3:
            output.append(f"  … +{len(l2p_err)-3} more")

    if output:
        print("\n".join(output))


if __name__ == "__main__":
    main()
