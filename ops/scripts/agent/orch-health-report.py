#!/usr/bin/env python3
"""orch-health-report.py — Live agent health snapshot for Telegram delivery.

no_agent watchdog pattern:
  Always outputs the snapshot (not silent) — this is a periodic report, not a state-change monitor.

Two health methods:
  - http:   Poll agent's health-vector HTTP endpoint (server agents)
  - inbox:  Read agent's latest health push from the PGMQ bus queue
            ``inbox_health_check`` (client-only agents)

Laptop agents (Titus): use inbox method with a 4-hour grace period.
  When offline but within grace, shows 🌙 offline instead of 🔴 unreachable.

Usage:
  python3 orch-health-report.py

Output:
  Compact markdown with emoji status per agent, one line per service.
  Designed for mobile Telegram display (narrow width, concise).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

HOME = Path.home()
CORTEX_ENV = HOME / "hermes-cortex" / ".env"

# Ensure lib.cortex_bus is importable (same pattern as orch-clean-health-queue.py)
try:
    from hermes_paths import ensure_scripts_path
    ensure_scripts_path()
except Exception:
    pass  # not fatal — bus read degrades to None

REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"
REGISTRY_TEMPLATE = HOME / "hermes-cortex" / "ops" / "install" / "deploy" / "agent-registry.template.json"
REGISTRY_LOCAL = HOME / ".hermes-cortex" / "state" / "agent-registry.local.json"
# External SSL-terminated endpoints need headroom. A 3s timeout was measured
# dying during :00 poller bursts (single-threaded health server + cold mycortex
# cache → 2-9s responses → BrokenPipe). 5s matches fleet poller guidance
# (agent-health-monitoring skill). See pitfall "External endpoint timeout sensitivity".
TIMEOUT = 5
SERVICE_MAP = ["resources", "services", "no_errored_crons", "no_stale_crons",
               "nginx", "ollama", "mycortex", "disk_ok", "gbrain_sources_ok"]
ICONS = {1: "🟢", 0: "⚪", -1: "🔴"}

# Laptop grace period — shared with orch-fleet-watchdog.py
LAPTOP_GRACE_MINUTES = 30  # 30 min — covers quick coffee breaks / lid closes
LAST_SEEN_FILE = HOME / ".hermes-cortex" / "state" / "last-seen.json"


# ── Last-seen tracking (laptop grace period, shared with orch-fleet-watchdog.py) ──


def _record_last_seen(agent_key: str, timestamp_iso: str) -> None:
    """Persist the latest anchor timestamp for an inbox agent."""
    if not LAST_SEEN_FILE.parent.exists():
        LAST_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    seen = {}
    if LAST_SEEN_FILE.exists():
        try:
            seen = json.loads(LAST_SEEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    seen[agent_key] = timestamp_iso
    LAST_SEEN_FILE.write_text(json.dumps(seen, indent=2))


def _last_seen_minutes_ago(agent_key: str) -> Optional[int]:
    """Return minutes since agent's last anchor timestamp, or None if unknown."""
    if not LAST_SEEN_FILE.exists():
        return None
    try:
        seen = json.loads(LAST_SEEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    ts_str = seen.get(agent_key, "")
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00").replace("T", " ")
        if "+" not in ts_str and ts_str.endswith("00:00"):
            ts_str += "+00:00"
        last = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = now - last
        return int(delta.total_seconds() / 60)
    except (ValueError, TypeError):
        return None


# ── Agent loading ──

def _get_agents() -> list[dict]:
    """Load agents from registry with local overrides, same as orch-fleet-watchdog.py."""
    agents = []
    registry = {}
    local_overrides = {}

    if REGISTRY_PATH.exists():
        try:
            registry = json.loads(REGISTRY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    if not registry and REGISTRY_TEMPLATE.exists():
        try:
            registry = json.loads(REGISTRY_TEMPLATE.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    if REGISTRY_LOCAL.exists():
        try:
            local_overrides = json.loads(REGISTRY_LOCAL.read_text()).get("agents", {})
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled

    for key, entry in registry.get("agents", {}).items():
        merged = dict(entry)
        if key in local_overrides:
            merged.update(local_overrides[key])
        if not merged.get("accessible", False):
            continue
        method = merged.get("health_method", "http")
        name = merged.get("name", key.capitalize())
        if method == "http":
            url = (merged.get("health_url") or "").strip()
            if url:
                agents.append({"key": key, "name": name, "method": "http", "url": url})
        elif method == "inbox":
            agents.append({"key": key, "name": name, "method": "inbox"})

    # Fallback: Moses health URL from .env, then localhost
    if not any(a["key"] == "moses" for a in agents):
        import os
        moses_url = os.environ.get("CORTEX_HEALTH_URL", "")
        if not moses_url and CORTEX_ENV.exists():
            for line in CORTEX_ENV.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "CORTEX_HEALTH_URL":
                    moses_url = v.strip().strip("'\"")
                    break
        if not moses_url:
            moses_url = "http://127.0.0.1:13007/health"
        agents.insert(0, {"key": "moses", "name": "Moses", "method": "http",
                          "url": moses_url})
    return agents


# ── HTTP fetch ──

def _fetch(url: str) -> Optional[dict]:
    """Fetch health vector from an agent via HTTP."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "hermes-health-report/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


# ── Inbox fetch ──

def _fetch_inbox_vector(agent_key: str) -> Optional[list[int]]:
    """Read the latest health push for an inbox-method agent.

    Client-only agents (health_method=inbox) push their health vector to the
    ``inbox_health_check`` PGMQ queue via ``health-vector-push.sh`` (POST
    /api/pgmq/send, body ``{"from":..., "subject":"health", "body":"{...}"}``).

    The ``orch-clean-health-queue`` cron (every 10m) drains that queue and
    persists each agent's latest vector + timestamp to
    ``~/.hermes-cortex/state/inbox-health-state.json`` — that file is the
    reliable source here (a live queue read at hourly report time would often
    find the queue already drained).

    Returns the vector or None. For laptop agents (inbox method), None can mean
    offline — the caller checks _last_seen_minutes_ago() for grace period.
    """
    state_file = HOME / ".hermes-cortex" / "state" / "inbox-health-state.json"
    try:
        if state_file.exists():
            state = json.loads(state_file.read_text())
            entry = state.get(agent_key)
            if entry and isinstance(entry.get("vector"), list):
                ts = entry.get("ts") or ""
                if ts:
                    _record_last_seen(agent_key, ts)
                return entry["vector"]
    except (json.JSONDecodeError, OSError):
        pass  # fall through to live queue read
    # Fallback: peek the live queue (covers a ping the cleaner hasn't drained yet)
    try:
        from lib.cortex_bus import bus_read
    except Exception:
        return None
    for _ in range(20):  # scan up to 20 pending pings
        msg = bus_read("inbox_health_check", vt=60)
        if not msg or not msg.get("msg_id"):
            break  # queue empty or unreachable
        body = msg.get("body", {})
        if not isinstance(body, dict):
            continue
        if (body.get("from") or "").strip().lower() != agent_key.lower():
            continue  # another agent's ping — leave it for the cleaner
        inner = body.get("body", "")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                inner = {}
        if isinstance(inner, dict) and "v" in inner and isinstance(inner["v"], list):
            ts_str = msg.get("enqueued_at") or ""
            if ts_str:
                _record_last_seen(agent_key, ts_str)
            return inner["v"]
    return None


# ── Report builder ──

def build_snapshot() -> str:
    """Build the health snapshot markdown string."""
    agents = _get_agents()
    kst = timezone(timedelta(hours=9))
    ts = datetime.now(kst).strftime("%a %H:%M KST")
    lines = [f"━━━ **Agent Health** — {ts} ━━━"]

    for agent in agents:
        key = agent["key"]
        name = agent["name"]
        vec = None

        if agent["method"] == "http":
            data = _fetch(agent["url"])
            if data and "v" in data:
                vec = data["v"]
        elif agent["method"] == "inbox":
            vec = _fetch_inbox_vector(key)

        if not vec:
            # Check laptop grace period for inbox agents
            if agent["method"] == "inbox":
                mins_ago = _last_seen_minutes_ago(key)
                if mins_ago is not None and mins_ago < LAPTOP_GRACE_MINUTES:
                    lines.append(f"\n**{name}** 🌙 offline ({mins_ago}m)")
                    continue
            lines.append(f"\n**{name}** 🔴 unreachable")
            continue

        down = sum(1 for x in vec if x == -1)
        status = "✅" if down == 0 else f"⚠️ {down} down"
        bar = "".join(ICONS.get(x, "⬜") for x in vec)

        lines.append(f"\n**{name}** {status}")
        lines.append(bar)

        failures = []
        for i, v in enumerate(vec):
            if v == -1 and i < len(SERVICE_MAP):
                failures.append(f"  {SERVICE_MAP[i]} 🔴")
        if failures:
            lines.extend(failures)

    return "\n".join(lines) + "\n"


def main():
    print(build_snapshot(), flush=True)


if __name__ == "__main__":
    main()
