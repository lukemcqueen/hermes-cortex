#!/usr/bin/env python3
"""orch-bus-inbox-relay.py — failover processing feed for the backup orchestrator.

When Esther is acting primary (failover-active marker present), agents'
fallback traffic lands in inbox_orchestrator on her LOCAL bus. Her normal
bus-processing crons read inbox_esther (the MCP inbox tool is queue-scoped
to the agent's own inbox), so orchestrator-inbox messages would sit
unprocessed for the whole outage. This relay moves them into the normal
processing pipeline: failover-period messages are re-sent from
inbox_orchestrator → inbox_esther (preserving from/subject/body), the
originals archived, and stale pre-outage mirror copies archived too (Moses
holds the originals — the standby copy is a warm-mirror duplicate).

Runs as a no_agent cron (every 5 min). No marker = silent no-op (empty
stdout = silent). Marker = summary line (delivered to the origin channel).

CUTOFF RULE (lossless):
  - enqueued_at >= failover start       → relay to inbox_esther + archive
  - margin [start - 10min, start)       → LEAVE (drains to Moses on recovery)
  - enqueued_at <  start - 10min        → archive (mirror copy; Moses has it)
The 10-min margin covers direct fallback arrivals that beat the watchdog's
first probe failure by seconds-to-minutes (agents fall back per-call the
moment the primary bus fails; the watchdog may not probe for another 5 min).
Leaving in-margin messages is lossless: on recovery the forwarder drains
them to Moses.

SAFETY: orchestrator-only by construction — only Esther ever writes the
marker (Moses never activates failover). Reads use vt=600 so an in-margin
message is temporarily hidden (not consumed) and the queue advances.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
HOSTNAME = os.uname().nodename.split(".")[0]
STATE_DIR = HOME / ".hermes-cortex" / "state"
MARKER_FILE = STATE_DIR / ".failover-active"
FAILOVER_STATE_FILE = STATE_DIR / "bus-failover-state.json"
CONF_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"

LOCAL_URL = "http://127.0.0.1:8903"
MAX_PER_TICK = 20
RELAY_QUEUE = "inbox_orchestrator"
TARGET_QUEUE = "inbox_esther"
MARGIN_MINUTES = 10  # safe window before first_failure_at (see docstring)


def _conf(key: str) -> str:
    """Read a KEY=value line from cortex-bus.conf (env wins)."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        if CONF_FILE.exists():
            for line in CONF_FILE.read_text().splitlines():
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def _failover_cutoff() -> datetime | None:
    """Failover start (UTC) from state file, else marker content, else mtime."""
    if not MARKER_FILE.exists():
        return None
    # Prefer the watchdog's recorded first-failure time (outage start).
    try:
        if FAILOVER_STATE_FILE.exists():
            state = json.loads(FAILOVER_STATE_FILE.read_text())
            first = state.get("first_failure_at")
            if first:
                return datetime.fromisoformat(first.replace("Z", "+00:00"))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    # Fall back to the marker's own timestamp (activation time).
    try:
        return datetime.fromisoformat(MARKER_FILE.read_text().strip().replace("Z", "+00:00"))
    except (OSError, ValueError):
        pass
    try:
        mtime = datetime.fromtimestamp(MARKER_FILE.stat().st_mtime, tz=timezone.utc)
        return mtime
    except OSError:
        return None


def _request(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = {"detail": f"HTTP {e.code}"}
        return e.code, detail
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, {"error": str(e)[:200]}


def _peek(token: str) -> dict | None:
    """Read one message with vt=600 (hidden 10 min — not consumed)."""
    status, data = _request(
        "POST", f"{LOCAL_URL}/api/pgmq/read", token,
        {"queue": RELAY_QUEUE, "vt": 600},
    )
    if status == 200 and isinstance(data, dict) and data.get("msg_id"):
        return data
    return None


def _send(token: str, body: dict) -> bool:
    status, _ = _request(
        "POST", f"{LOCAL_URL}/api/pgmq/send", token,
        {"queue": TARGET_QUEUE, "message": body},
    )
    return status == 200


def _archive(token: str, msg_id: str) -> bool:
    status, _ = _request(
        "POST", f"{LOCAL_URL}/api/pgmq/archive", token,
        {"queue": RELAY_QUEUE, "msg_id": msg_id},
    )
    return status == 200


def _parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def run_once() -> list[str]:
    cutoff = _failover_cutoff()
    if cutoff is None:
        return []  # no failover — silent
    token = _conf("CORTEX_BUS_TOKEN")
    if not token:
        return ["❌ orch-bus-inbox-relay: CORTEX_BUS_TOKEN missing — cannot relay"]
    margin_start = cutoff - timedelta(minutes=MARGIN_MINUTES)
    now = datetime.now(timezone.utc)

    relayed = archived = left = 0
    for _ in range(MAX_PER_TICK):
        msg = _peek(token)
        if msg is None:
            break
        ts = _parse_ts(msg.get("enqueued_at", "")) or now
        msg_id = msg["msg_id"]
        body = msg.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                body = {"raw": body}
        if not isinstance(body, dict):
            body = {"raw": str(body)}

        if ts < margin_start:
            # Stale mirror copy — Moses holds the original. Archive to advance.
            if _archive(token, msg_id):
                archived += 1
            continue
        if ts < cutoff:
            # In-margin: possible direct arrival before the first probe failure.
            # Leave it — reappears after the vt window; forwarder drains on recovery.
            left += 1
            continue

        # Failover-period direct arrival — relay into the processing pipeline.
        out = dict(body)
        out["relayed_from"] = RELAY_QUEUE
        if msg.get("correlation_id"):
            out["correlation_id"] = msg["correlation_id"]
        if _send(token, out) and _archive(token, msg_id):
            relayed += 1
        else:
            return [
                f"❌ orch-bus-inbox-relay: send/archive failed at msg {msg_id[:8]} — "
                f"will retry next tick"
            ]

    lines = []
    if relayed:
        lines.append(f"🔁 FAILOVER RELAY: moved {relayed} orchestrator-inbox message(s) "
                     f"→ {TARGET_QUEUE} for processing")
    if archived:
        lines.append(f"🧹 FAILOVER RELAY: archived {archived} stale mirror copy(ies) (originals on Moses)")
    if left:
        lines.append(f"⏳ FAILOVER RELAY: left {left} in-margin message(s) for Moses-drain on recovery")
    return lines


def main() -> int:
    for line in run_once():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
