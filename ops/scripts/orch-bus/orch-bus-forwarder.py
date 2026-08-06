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
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "bus-forwarder-state.json"
TIMEOUT = 10
MAX_PER_QUEUE = 10
MAX_SEEN = 10000  # compact state when seen set exceeds this
PEER_HEALTH_TIMEOUT = 5  # quick health check before attempting sync


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
            print("expected — silently handled", file=sys.stderr)
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


# ── Config from env vars (with conf-file fallback) ──
# NOTE (2026-08-05): ALL of these must resolve via _resolve_var (env →
# cortex-bus.conf → ~/hermes-cortex/.env), NOT os.environ alone. The
# failover watchdog rewrites CORTEX_BUS_URL / CORTEX_BUS_FALLBACK_URL in
# cortex-bus.conf when it activates/recovers — an env-only read ignores
# the swap, and cron runs (no env) resolve to empty peers/tokens, so the
# LOCAL→PEER drain silently failed. Found 2026-08-05: 2 worker replies
# stranded on Esther's bus despite Moses being reachable.
LOCAL_URL = _resolve_var("BUS_FORWARDER_LOCAL_URL", "http://127.0.0.1:8903")
LOCAL_TOKEN = _resolve_var("BUS_FORWARDER_LOCAL_TOKEN") or _resolve_var("CORTEX_BUS_TOKEN")
# ── Peer URL: role-aware. The peer is the OTHER orchestrator's bus. ──
#   On Moses (primary): peer = Esther = CORTEX_BUS_FALLBACK_URL (:14004)
#   On Esther (backup): peer = Moses = CORTEX_BUS_URL       (:13004)
# The old default (always CORTEX_BUS_FALLBACK_URL) self-synced on Esther:
# her fallback URL points at her own external :14004, so the forwarder was
# syncing Esther↔Esther and never saw Moses' inbox. (found 2026-08-03,
# take-charge assessment — worker fix requests invisible in the mirror)
_HOST = os.uname().nodename.split(".")[0]
if _resolve_var("BUS_FORWARDER_PEER_URL"):
    PEER_URL = _resolve_var("BUS_FORWARDER_PEER_URL")
elif _HOST == "moses":
    PEER_URL = _resolve_var("CORTEX_BUS_FALLBACK_URL", "")
else:
    # esther (and any non-moses orchestrator): peer = the OTHER host's bus.
    # CORTEX_BUS_URL flips with failover state — the failover watchdog swaps
    # it between Moses :13004 (standby) and local :8903 (while acting
    # primary). NEVER peer with localhost: the forwarder would self-sync and
    # the backlog would never drain to Moses when he returns (found
    # 2026-08-05: failover messages stranded on Esther's bus for hours).
    _primary = _resolve_var("CORTEX_BUS_URL", "")
    _is_local = _primary.startswith(("http://127.0.0.1", "http://localhost"))
    if _is_local:
        PEER_URL = _resolve_var("CORTEX_BUS_FALLBACK_URL", "")
    else:
        PEER_URL = _primary or _resolve_var("CORTEX_BUS_FALLBACK_URL", "")
# External peer (nginx) authenticates with Basic auth, not Bearer.
PEER_AUTH = (
    _resolve_var("BUS_FORWARDER_PEER_AUTH")
    or _resolve_var("CORTEX_BUS_FALLBACK_AUTH")
    or _resolve_var("CORTEX_BASIC_AUTH")
)
PEER_TOKEN = _resolve_var("BUS_FORWARDER_PEER_TOKEN") or LOCAL_TOKEN

# Queues to sync — auto-discovered from local bus if possible
QUEUES: list[str] = []


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
        print("expected — silently handled", file=sys.stderr)
        return ["inbox_moses", "inbox_esther", "inbox_joseph",
                "inbox_titus", "inbox_gisu", "inbox_kustos"]


def _request(
    method: str,
    url: str,
    token: str = "",
    auth: str = "",
    body: Optional[dict] = None,
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


def _peek_bus(
    url: str, token: str, auth: str, queue: str, limit: int = MAX_PER_QUEUE
) -> list[dict]:
    """Peek pending messages WITHOUT consuming (non-destructive batch read).

    Uses GET /api/pgmq/peek/{queue} — returns up to `limit` pending messages
    with NO state change (no 'processing' transition, no visibility timeout).
    The mirror must never consume: consumption belongs to the orchestrator
    that actually does the work (primary normally; backup when primary is
    down and it becomes active).
    """
    status, data = _request(
        "GET", f"{url}/api/pgmq/peek/{queue}?limit={limit}",
        token=token, auth=auth,
    )
    if status in (200,) and isinstance(data, dict):
        return data.get("messages", [])
    return []


def _send_bus(
    url: str, token: str, auth: str, queue: str, body: dict | str
) -> bool:
    """Send a message to a bus. Returns True on success."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass  # expected — silently handled
    status, _ = _request(
        "POST", f"{url}/api/pgmq/send",
        token=token, auth=auth,
        body={"queue": queue, "message": body},
    )
    return status == 200


def _archive_bus(
    url: str, token: str, auth: str, queue: str, msg_id: str
) -> bool:
    """Archive a message on a bus (removes it from the live queue)."""
    status, _ = _request(
        "POST", f"{url}/api/pgmq/archive",
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


def _parse_body(raw: object) -> dict:
    """Normalize a message body to a dict.

    The read API returns `body` as a dict for most messages, but
    double-encoded messages arrive as a JSON *string* (the SQL
    jsonb_build_object serializes the nested jsonb). Wrapping such a
    string in {"raw": ...} loses subject/from/topic — the handler then
    sees "Unknown subject '' from ?" (observed 2026-08-05). Parse the
    string instead; fall back to raw-wrap only if it is not valid JSON.
    """
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass  # expected — silently handled
    return {"raw": str(raw)}


def _dedup_key(msg: dict, body: dict) -> str:
    """Stable identity for loop prevention.

    bus.send() mints a FRESH UUID per send, so msg_id changes on every
    forwarder hop (local→peer, peer→local) and a bounced message can
    never be caught by a msg_id-based seen set — that was the ping-pong
    loop (found 2026-08-05: notices bounced Esther↔Moses every 2 min).
    correlation_id is preserved by the forwarder, so it survives hops.
    Fall back to a body hash when correlation_id is absent.
    """
    corr = msg.get("correlation_id") or body.get("correlation_id") or ""
    if corr:
        return f"corr:{corr}"
    canonical = json.dumps(body, sort_keys=True, default=str)
    return f"hash:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def _sync_direction(
    state: dict,
    source_url: str,
    source_token: str,
    source_auth: str,
    dest_url: str,
    dest_token: str,
    dest_auth: str,
    direction: str,
    can_archive_source: bool = False,
) -> tuple[list[str], list[str]]:
    """Mirror pending messages from source bus to destination bus.

    NEVER consumes from a primary bus. The forwarder is a MIRROR — the only
    consumer of a primary bus is the orchestrator that does the work
    (primary normally; backup when the primary is down and it goes active).

    Archive rule (role-aware, 2026-08-06):
      - can_archive_source=True  → source is the BACKUP bus (recovery drain:
        backup cleared after its backlog is delivered to the primary, which
        is now the active consumer).
      - can_archive_source=False → source is the PRIMARY bus: never archive.
        Seen messages are skipped (peek is non-destructive, batch — no
        head-blocking), and the real consumer pops them when it does work.

    Returns (forwarded_ids, error_ids) for this direction.
    """
    seen_key = f"seen_{direction}"
    total_key = f"total_{direction}"
    seen = set(state.get(seen_key, []))
    total = state.get(total_key, 0)
    forwarded: list[str] = []
    errors: list[str] = []

    for queue in QUEUES:
        msgs = _peek_bus(source_url, source_token, source_auth, queue)
        for msg in msgs:
            msg_id = str(msg.get("msg_id", ""))
            body = _parse_body(msg.get("body", {}))
            dkey = _dedup_key(msg, body)
            if dkey in seen:
                # Already mirrored. NEVER archive a primary source — the real
                # consumer (active orchestrator) pops it when doing work.
                # Batch peek means no head-blocking, so skipping is safe.
                continue

            # Preserve correlation_id when forwarding
            corr_id = msg.get("correlation_id") or body.get("correlation_id") or ""
            if corr_id:
                body["correlation_id"] = corr_id

            if _send_bus(dest_url, dest_token, dest_auth, queue, body):
                seen.add(dkey)
                forwarded.append(f"{queue}/{dkey[-10:]}")
                total += 1
                # Backup-source drain: clear the copy once delivered to the
                # primary (now the active consumer). Primary sources are
                # never archived here.
                if can_archive_source and msg_id:
                    _archive_bus(source_url, source_token, source_auth, queue, msg_id)
            else:
                errors.append(f"{queue}/{dkey[-10:]}")
                break  # destination unreachable — stop this queue

    state[seen_key] = list(seen)
    state[total_key] = total
    _compact_state(state, direction)
    return forwarded, errors


def main():
    global QUEUES, LOCAL_URL, LOCAL_TOKEN, PEER_URL, PEER_TOKEN, PEER_AUTH, IS_PRIMARY

    # ── Role: primary (moses) vs backup (esther) ────────────
    # The forwarder is role-aware (2026-08-06): the PRIMARY bus is where
    # workers + the active orchestrator consume — the forwarder NEVER
    # archives on it. The BACKUP bus is the mirror copy; archiving there is
    # the recovery drain (clear the copy once delivered to the primary).
    _host = os.uname().nodename.split(".")[0]
    IS_PRIMARY = (_host == "moses")

    # Resolve via config files if not set
    if not LOCAL_TOKEN:
        LOCAL_TOKEN = _resolve_var("CORTEX_BUS_TOKEN")
    if not PEER_URL:
        # Role-aware peer resolution (same rule as module level):
        # moses → CORTEX_BUS_FALLBACK_URL (Esther :14004)
        # esther → CORTEX_BUS_URL (Moses :13004)
        _h = os.uname().nodename.split(".")[0]
        if _h == "moses":
            PEER_URL = _resolve_var("CORTEX_BUS_FALLBACK_URL", "")
        else:
            PEER_URL = _resolve_var("CORTEX_BUS_URL", "") or _resolve_var("CORTEX_BUS_FALLBACK_URL", "")
    if not PEER_TOKEN:
        PEER_TOKEN = LOCAL_TOKEN
    if not PEER_AUTH:
        PEER_AUTH = _resolve_var("CORTEX_BUS_FALLBACK_AUTH", "") or _resolve_var("CORTEX_BASIC_AUTH", "")

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
            # Source = PEER. If we are the PRIMARY (moses), the peer is the
            # BACKUP (esther) → recovery drain: archiving the backup copy is
            # safe once delivered here. If we are the BACKUP, the peer is the
            # PRIMARY → never archive (workers read it).
            can_archive_source=IS_PRIMARY,
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
            # Source = LOCAL. If we are the BACKUP (esther), our local bus is
            # the backup → draining it to the recovering primary is safe to
            # archive. If we are the PRIMARY, our local bus IS the primary →
            # never archive (workers read it).
            can_archive_source=not IS_PRIMARY,
        )

    state["last_run"] = datetime.now(timezone.utc).isoformat()

    # ── Output (no_agent: silent until issue) ──
    # Only prints when something noteworthy happens:
    #   - Peer went down (from up state)
    #   - Peer came back (with drain summary)
    #   - Sync errors occurred
    output = []
    now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%H:%M KST")

    # Clear peer_downed_at on successful sync (before writing state)
    was_peer_down = "peer_downed_at" in state

    if peer_ok:
        if was_peer_down:
            state.pop("peer_downed_at", "")
            p2l_count = len(p2l_fwd)
            l2p_count = len(l2p_fwd)
            output.append(f"✅ [{now_str}] Peer recovered — drained {p2l_count}→local, {l2p_count}→peer")
        elif p2l_err or l2p_err:
            if p2l_err:
                output.append(f"⚠️  [{now_str}] PEER→LOCAL: {len(p2l_err)} failed")
                for f in p2l_err[:3]:
                    output.append(f"  • {f}")
            if l2p_err:
                output.append(f"⚠️  [{now_str}] LOCAL→PEER: {len(l2p_err)} failed")
                for f in l2p_err[:3]:
                    output.append(f"  • {f}")
        # else: silent — normal sync, nothing to report
    else:
        if not was_peer_down:
            state["peer_downed_at"] = datetime.now(timezone.utc).isoformat()
            output.append(f"🔴 [{now_str}] Peer unreachable — sync paused")
        # else: still down, silent — no repeated alerts

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

    if output:
        print("\n".join(output))


if __name__ == "__main__":
    main()
