#!/usr/bin/env python3
"""
bus-forwarder.py — Bidirectional bus sync for primary/backup failover.

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

CONFIGURATION
  All via env vars (set in ~/.hermes-cortex/cortex-bus.conf or ~/hermes-cortex/.env):

  BUS_FORWARDER_LOCAL_URL     Local bus (default: http://127.0.0.1:8903)
  BUS_FORWARDER_LOCAL_TOKEN   Token for local bus (default: CORTEX_BUS_TOKEN)
  BUS_FORWARDER_PEER_URL      Peer bus address (default: CORTEX_BUS_FALLBACK_URL)
  BUS_FORWARDER_PEER_AUTH     Basic auth for peer nginx proxy (optional)
  BUS_FORWARDER_PEER_TOKEN    Token for peer bus (default: same as local)

  Defaults work on Moses: local = 127.0.0.1:8903, peer = bus.example.org:14004

USAGE
  Run as a no_agent cron: */2 * * * *
  Empty output = silent (nothing new to sync).
  Non-empty = message count + errors.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "bus-forwarder-state.json"
TIMEOUT = 10
MAX_PER_QUEUE = 10
MAX_SEEN = 10000  # compact state when seen set exceeds this
PEER_HEALTH_TIMEOUT = 5  # quick health check before attempting sync

# ── Config from env vars ──
LOCAL_URL = os.environ.get(
    "BUS_FORWARDER_LOCAL_URL",
    "http://127.0.0.1:8903",
)
LOCAL_TOKEN = os.environ.get(
    "BUS_FORWARDER_LOCAL_TOKEN",
    os.environ.get("CORTEX_BUS_TOKEN", ""),
)
PEER_URL = os.environ.get(
    "BUS_FORWARDER_PEER_URL",
    os.environ.get("CORTEX_BUS_FALLBACK_URL", ""),
)
PEER_AUTH = os.environ.get("BUS_FORWARDER_PEER_AUTH", "")
PEER_TOKEN = os.environ.get(
    "BUS_FORWARDER_PEER_TOKEN",
    LOCAL_TOKEN,  # default: same token (shared across fleet)
)

# Queues to sync — auto-discovered from local bus if possible
QUEUES: list[str] = []


def _load_config_file(path: Path) -> dict:
    """Load env vars from a config file."""
    env = {}
    if path.exists():
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
        except OSError:
            pass
    return env


def _resolve_var(key: str, default: str = "") -> str:
    """Resolve env var from env → config file → default."""
    val = os.environ.get(key)
    if val:
        return val
    # Try config files
    for cfg_path in [
        HOME / ".hermes-cortex" / "cortex-bus.conf",
        HOME / "hermes-cortex" / ".env",
    ]:
        cfg = _load_config_file(cfg_path)
        if key in cfg and cfg[key]:
            return cfg[key]
    return default


def _discover_queues() -> list[str]:
    """Fetch the queue list from the local bus API. Falls back to hardcoded list."""
    token = LOCAL_TOKEN
    url = f"{LOCAL_URL}/api/pgmq/queues"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
        }, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        queues = data.get("queues", []) if isinstance(data, dict) else data
        # Only sync inbox queues (skip DLQs — they're per-instance)
        inbox = sorted(set(
            q["name"] for q in queues
            if q.get("name", "").startswith("inbox_")
            and not q.get("dlq", False)
            and "health_check" not in q.get("name", "")
        ))
        return inbox
    except Exception:
        # Fallback to hardcoded list
        return ["inbox_moses", "inbox_esther", "inbox_joseph",
                "inbox_titus", "inbox_gisu", "inbox_kustos"]


def _request(
    method: str,
    url: str,
    token: str = "",
    auth: str = "",
    body: dict | None = None,
) -> tuple[int, dict]:
    """Make an HTTP request. Returns (status_code, response_dict).
    
    For peer connections (e.g. Esther): nginx requires Basic auth on the
    external port. The Bearer token is only used internally or when both
    are provided (Basic for nginx, Bearer forwarded to bus server).
    """
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None

    if auth:
        encoded = base64.b64encode(auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = {"detail": f"HTTP {e.code}"}
        return e.code, detail
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, {"error": str(e)[:200]}


def _read_bus(
    url: str, token: str, auth: str, queue: str
) -> dict | None:
    """Read (peek with vt=0 — non-destructive) one message.
    
    With the vt=0 peek fix on the bus server, this reads the message body
    WITHOUT changing its state. The message stays pending and is visible
    to subsequent reads. After forwarding, _archive_bus() is called to
    consume the message from the source queue.
    """
    status, data = _request(
        "POST", f"{url}/api/pgmq/read",
        token=token, auth=auth,
        body={"queue": queue, "vt": 0},
    )
    if status in (200,) and isinstance(data, dict) and data.get("msg_id"):
        return data
    return None


def _send_bus(
    url: str, token: str, auth: str, queue: str, body: dict | str
) -> bool:
    """Send a message to a bus. Returns True on success."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass
    status, _ = _request(
        "POST", f"{url}/api/pgmq/send",
        token=token, auth=auth,
        body={"queue": queue, "message": body},
    )
    return status == 200


def _archive_bus(
    url: str, token: str, auth: str, queue: str, msg_id: str
) -> bool:
    """Archive (DELETE) a message from a bus queue after successful forwarding.
    
    This prevents the source message from cycling through processing→recover→pending
    when vt=0 is used for reading. Without this, every forwarded message burns a
    full retry cycle on the source bus.
    """
    if not msg_id:
        return False
    status, _ = _request(
        "DELETE", f"{url}/api/pgmq/delete",
        token=token, auth=auth,
        body={"queue": queue, "msg_id": msg_id},
    )
    return status == 200


def _compact_state(state: dict, direction: str) -> None:
    """Trim seen set if it exceeds MAX_SEEN.
    
    Keeps the most recent MAX_SEEN/2 entries to maintain
    dedup coverage for the most active period.
    """
    seen_key = f"seen_{direction}"
    seen = state.get(seen_key, [])
    if len(seen) > MAX_SEEN:
        # Keep the later half (most recent)
        state[seen_key] = seen[-(MAX_SEEN // 2):]


def _sync_direction(
    state: dict,
    source_url: str,
    source_token: str,
    source_auth: str,
    dest_url: str,
    dest_token: str,
    dest_auth: str,
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
            msg = _read_bus(source_url, source_token, source_auth, queue)
            if msg is None:
                break
            msg_id = msg["msg_id"]
            if msg_id in seen:
                continue

            body = msg.get("body", {})
            # Preserve correlation_id when forwarding
            if not isinstance(body, dict):
                body = {"raw": str(body)}

            corr_id = msg.get("correlation_id", body.get("correlation_id", ""))
            if corr_id:
                body["correlation_id"] = corr_id

            if _send_bus(dest_url, dest_token, dest_auth, queue, body):
                seen.add(msg_id)
                forwarded.append(f"{queue}/{msg_id[:8]}")
                total += 1
                # Archive source message ONLY for orchestrator queues (moses, esther)
                # where the message was already processed locally. For server-agent
                # queues (gisu, kustos, joseph, titus), the agent must archive it
                # after processing — the forwarder only copies for warm standby.
                if queue in ("inbox_moses", "inbox_esther"):
                    _archive_bus(source_url, source_token, source_auth, queue, msg_id)
            else:
                errors.append(f"{queue}/{msg_id[:8]}")
                break  # destination unreachable — stop this queue

    state[seen_key] = list(seen)
    state[total_key] = total
    _compact_state(state, direction)
    return forwarded, errors


def main():
    global QUEUES, LOCAL_URL, LOCAL_TOKEN, PEER_URL, PEER_TOKEN, PEER_AUTH

    # Resolve via config files if not set
    if not LOCAL_TOKEN:
        LOCAL_TOKEN = _resolve_var("CORTEX_BUS_TOKEN")
    if not PEER_URL:
        PEER_URL = _resolve_var("CORTEX_BUS_FALLBACK_URL")
    if not PEER_TOKEN:
        PEER_TOKEN = LOCAL_TOKEN
    if not PEER_AUTH:
        PEER_AUTH = _resolve_var("CORTEX_BUS_FALLBACK_AUTH", "")

    # Discover queues
    QUEUES = _discover_queues()

    # Validate config
    if not LOCAL_URL or not LOCAL_TOKEN:
        print("ERROR: LOCAL_URL and LOCAL_TOKEN required", file=sys.stderr)
        sys.exit(1)
    if not PEER_URL:
        print("ERROR: PEER_URL (CORTEX_BUS_FALLBACK_URL) required — no peer to sync with",
              file=sys.stderr)
        sys.exit(1)

    # Quick peer health check — skip sync if peer is down (no hang)
    # External buses use nginx Basic auth (not Bearer token)
    peer_ok = True
    try:
        req = urllib.request.Request(f"{PEER_URL}/health", method="GET")
        if PEER_AUTH:
            encoded = base64.b64encode(PEER_AUTH.encode()).decode()
            req.add_header("Authorization", f"Basic {encoded}")
        elif PEER_TOKEN:
            req.add_header("Authorization", f"Bearer {PEER_TOKEN}")
        with urllib.request.urlopen(req, timeout=PEER_HEALTH_TIMEOUT) as resp:
            pass
    except Exception:
        peer_ok = False

    # Load state
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    state.setdefault("total_peer_to_local", 0)
    state.setdefault("total_local_to_peer", 0)
    state.setdefault("seen_peer_to_local", [])
    state.setdefault("seen_local_to_peer", [])

    # ── Direction 1: PEER → LOCAL (warm standby sync) ──
    p2l_fwd: list[str] = []
    p2l_err: list[str] = []
    if peer_ok:
        p2l_fwd, p2l_err = _sync_direction(
            state,
            PEER_URL, PEER_TOKEN, PEER_AUTH,
            LOCAL_URL, LOCAL_TOKEN, "",
            "peer_to_local",
        )
    else:
        # Peer down — log it and skip
        state.setdefault("peer_downed_at",
                         datetime.now(timezone.utc).isoformat())

    # ── Direction 2: LOCAL → PEER (backlog drain on recovery) ──
    l2p_fwd: list[str] = []
    l2p_err: list[str] = []
    if peer_ok:
        l2p_fwd, l2p_err = _sync_direction(
            state,
            LOCAL_URL, LOCAL_TOKEN, "",
            PEER_URL, PEER_TOKEN, PEER_AUTH,
            "local_to_peer",
        )

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

    # ── Output (no_agent: empty = silent, only alert on errors) ──
    output = []
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

    if p2l_fwd:
        output.append(f"📥 [{now_str}] PEER→LOCAL: {len(p2l_fwd)} message(s) synced")
        for f in p2l_fwd[:5]:
            output.append(f"  • {f}")
        if len(p2l_fwd) > 5:
            output.append(f"  … +{len(p2l_fwd)-5} more")

    if l2p_fwd:
        output.append(f"📤 [{now_str}] LOCAL→PEER: {len(l2p_fwd)} message(s) synced")
        for f in l2p_fwd[:5]:
            output.append(f"  • {f}")
        if len(l2p_fwd) > 5:
            output.append(f"  … +{len(l2p_fwd)-5} more")

    if p2l_err:
        output.append(f"⚠️  [{now_str}] PEER→LOCAL: {len(p2l_err)} failed — peer unreachable?")
        for f in p2l_err[:3]:
            output.append(f"  • {f}")

    if l2p_err:
        output.append(f"⚠️  [{now_str}] LOCAL→PEER: {len(l2p_err)} failed — peer unreachable?")
        for f in l2p_err[:3]:
            output.append(f"  • {f}")

    # Summary line — only print when there's actual activity
    now = datetime.now(timezone.utc)
    last_run = state.get("last_run", "")
    p2l_total = state.get("total_peer_to_local", 0)
    l2p_total = state.get("total_local_to_peer", 0)
    has_activity = bool(p2l_fwd or l2p_fwd or p2l_err or l2p_err)
    if has_activity:
        seen_count = len(state.get("seen_peer_to_local", [])) + len(state.get("seen_local_to_peer", []))
        output.append(f"Stats: {p2l_total} peer→local | {l2p_total} local→peer | {seen_count} tracked")

    if output:
        print("\n".join(output))


if __name__ == "__main__":
    main()
