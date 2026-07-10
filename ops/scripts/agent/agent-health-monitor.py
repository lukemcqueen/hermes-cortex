#!/usr/bin/env python3
"""agent-health-monitor.py — Cross-server health poller for Moses (DEPRECATED).

⚠  This script is deprecated. Use orch-team-health.py instead, which
   supports the agent-registry.json health_method field (both 'http' for
   servers and 'inbox' for client-only agents like Titus).

   The active cron (orch-team-health) handles Titus via inbox — he pushes
   his health vector using health-vector-push.sh and Moses reads it from
   the inbox. Never try to HTTP-poll Titus directly. He is not a server.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (new issues or resolutions)

State tracked in ~/.hermes-cortex/state/health-state.json — fingerprints
per server so alerts only fire on state transitions.

Structured health data written to ~/.hermes-cortex/state/agent-health-data.json
for dashboard consumption — updated every poll cycle.

Agent registry at ~/.hermes-cortex/state/agent-registry.json — each agent
entry can set "health_url" for remote health API endpoint.
Moses's own health is checked at http://127.0.0.1:8905 via fallback.

Setup:
  Add to agent-registry.json:
    "gisu": { ..., "health_url": "https://user:pass@your-gisu-host:13006/api/v1/health" }
    "titus": { "health_method": "inbox" }  ⚠ Do NOT set health_url for Titus
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Import timezone helper
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
from hermes_tz import format_timestamp

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "health-state.json"
HEALTH_DATA_FILE = HOME / ".hermes" / "state" / "agent-health-data.json"
REGISTRY_PATH = HOME / ".hermes" / "state" / "agent-registry.json"
TIMEOUT = 15


def _get_agents() -> list[dict]:
    """Load health endpoints from registry. Fallback to local Moses health."""
    agents = []
    if REGISTRY_PATH.exists():
        try:
            data = json.loads(REGISTRY_PATH.read_text())
            for key, val in data.get("agents", {}).items():
                url = (val.get("health_url") or "").strip()
                if url:
                    agents.append({"key": key, "name": val.get("name", key), "url": url})
        except (json.JSONDecodeError, KeyError):
            pass
    # Always include Moses local
    if not any(a["key"] == "moses" for a in agents):
        agents.insert(0, {"key": "moses", "name": "Moses", "url": "http://127.0.0.1:8905/api/v1/health"})
    return agents


def _fetch(url: str) -> dict | None:
    """Fetch health endpoint. Returns None if unreachable, else parsed JSON."""
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "hermes-health-monitor/1.0"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return None


def _fingerprint(data: dict | None) -> str:
    """Stable fingerprint for change detection."""
    if data is None:
        return "unreachable"
    parts = [f"ok={data.get('healthy', False)}"]
    for iss in data.get("issues", []):
        parts.append(f"{iss.get('check')}:{iss.get('severity')}:{iss.get('detail')}")
    services = ((data.get("checks") or {}).get("services") or {}).get("items", [])
    for svc in services:
        parts.append(f"svc:{svc.get('name')}={svc.get('status')}")
    return "|".join(parts)


def _build_structured_data(agents: list[dict], poll_results: dict) -> dict:
    """Build structured health snapshot for dashboard consumption."""
    now_iso = datetime.now(timezone.utc).isoformat()
    health_data = {}

    for a in agents:
        key = a["key"]
        data = poll_results.get(key, {}).get("data")
        error = poll_results.get(key, {}).get("error")

        if data is None:
            health_data[key] = {
                "healthy": False,
                "reachable": False,
                "server": a["name"],
                "issues": [{"severity": "critical", "detail": "Unreachable", "error": error or "timeout/connection failed"}],
                "services": [],
                "last_seen": now_iso,
            }
        else:
            services = ((data.get("checks") or {}).get("services") or {}).get("items", [])
            issues = data.get("issues", [])
            health_data[key] = {
                "healthy": data.get("healthy", False),
                "reachable": True,
                "server": data.get("server", a["name"]),
                "hostname": data.get("hostname", ""),
                "issues": issues,
                "issue_count": len(issues),
                "critical_count": sum(1 for i in issues if i.get("severity") == "critical"),
                "services": services,
                "service_summary": f"{sum(1 for s in services if s.get('status') == 'running')}/{len(services)} up",
                "uptime_seconds": data.get("uptime_seconds", 0),
                "resources": data.get("checks", {}).get("resources", {}).get("data", {}),
                "last_seen": now_iso,
            }

    return health_data


def main():
    agents = _get_agents()

    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    now = {}
    alerts = []
    resolves = []
    poll_results = {}  # key -> {"data": ..., "error": ...}

    for a in agents:
        key = a["key"]
        name = a["name"]
        data = _fetch(a["url"])
        poll_results[key] = {"data": data, "error": None if data is not None else "unreachable"}
        fp = _fingerprint(data)
        now[key] = fp
        old = prev.get(key, "")

        if fp == old:
            continue  # No change

        if data is None:
            # Was reachable, now unreachable
            alerts.append(f"🔴 {name} — unreachable")
        elif data.get("_unreachable"):
            alerts.append(f"🔴 {name} — unreachable: {data.get('_error', '?')}")
        elif not data.get("healthy", True):
            issues = data.get("issues", [])
            lines = []
            for iss in issues[:5]:
                icon = {"critical": "🔴", "high": "⚠️", "warning": "⚡"}.get(iss.get("severity"), "ℹ️")
                lines.append(f"{icon} {iss['detail']}")
            if len(issues) > 5:
                lines.append(f"… +{len(issues)-5} more")
            alerts.append(f"🔴 {name}\n" + "\n".join(lines))
        elif data.get("healthy", False):
            if old and "ok=True" not in old:
                resolves.append(f"✅ {name} — health restored")
            elif old == "unreachable":
                resolves.append(f"✅ {name} — back online")

    # Save fingerprint state (change detection)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(now, indent=2))

    # Save structured health data (dashboard consumption) — always updated
    health_data = _build_structured_data(agents, poll_results)
    HEALTH_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_DATA_FILE.write_text(json.dumps(health_data, indent=2))

    # Output — no_agent cron delivers non-empty stdout
    output = []
    ts = format_timestamp("%Y-%m-%d %H:%M %Z")
    if alerts:
        output.append(f"━━━ Health Alert — {len(alerts)} issue(s) ━━━ [{ts}]")
        output.extend(alerts)
    if resolves:
        output.append(f"━━━ Health Restored ━━━ [{ts}]")
        output.extend(resolves)

    if output:
        print("\n\n".join(output))


if __name__ == "__main__":
    main()
