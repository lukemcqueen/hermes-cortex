#!/usr/bin/env python3
"""agent-health-monitor.py — Cross-server health poller for Moses.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (new issues or resolutions)

State tracked in ~/.hermes/state/health-state.json — fingerprints
per server so alerts only fire on state transitions.

Agent registry at ~/.hermes/state/agent-registry.json — each agent
entry can set "health_url" for remote health API endpoint.
Moses's own health is checked at http://127.0.0.1:8905 via fallback.

Setup:
  Add to agent-registry.json:
    "titus": { ..., "health_url": "https://user:pass@titus-host:13006/api/v1/health" }
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

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "health-state.json"
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

    for a in agents:
        key = a["key"]
        name = a["name"]
        data = _fetch(a["url"])
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

    # Save state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(now, indent=2))

    # Output — no_agent cron delivers non-empty stdout
    output = []
    if alerts:
        output.append(f"━━━ Health Alert — {len(alerts)} issue(s) ━━━")
        output.extend(alerts)
    if resolves:
        output.append(f"━━━ Health Restored ━━━")
        output.extend(resolves)

    if output:
        print("\n\n".join(output))


if __name__ == "__main__":
    main()