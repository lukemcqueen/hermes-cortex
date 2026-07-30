#!/usr/bin/env python3
"""orch-fleet-watchdog.py — Fleet health + workflow monitor for orchestrators.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (new issues or resolutions)

Polls every agent's health endpoint every 5 min, tracks active workflows
via the Agent Bus, detects stalled steps (>5 min running).

State tracked in ~/.hermes-cortex/state/fleet-state.json for change detection.
Structured dashboard data in ~/.hermes-cortex/state/fleet-data.json.

Setup:
  Add agents to ~/.hermes-cortex/state/agent-registry.json:
    {"agents": {"gisu": {"name": "Gisu", "health_url": "https://..."}, ...}}
  If registry missing, polls localhost:8905 as fallback.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from hermes_tz import format_timestamp
except ImportError:
    def format_timestamp(fmt: str) -> str:
        return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")


HOME = Path.home()
STATE_FILE = HOME / ".hermes-cortex" / "state" / "fleet-state.json"
DASHBOARD_FILE = HOME / ".hermes-cortex" / "state" / "fleet-data.json"
REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"
INBOX_DIR = HOME / ".hermes" / "inbox"
TIMEOUT = 10

# Well-known agent ports (fallback when registry missing)
AGENT_PORTS: dict[str, int] = {
    "moses": 8905,
    "esther": 8905,
}


def _get_agents() -> list[dict]:
    """Load agents from registry, fall back to known ports."""
    agents = []
    if REGISTRY_PATH.exists():
        try:
            data = json.loads(REGISTRY_PATH.read_text())
            for key, val in data.get("agents", {}).items():
                url = (val.get("health_url") or "").strip()
                agent = {"key": key, "name": val.get("name", key)}
                if url:
                    agent["url"] = url
                else:
                    port = AGENT_PORTS.get(key, 8905)
                    agent["url"] = f"http://127.0.0.1:{port}/api/v1/health"
                agents.append(agent)
        except (json.JSONDecodeError, KeyError):
            pass  # expected — silently handled

    if not agents:
        # Fallback: local health only
        agents.append({"key": "local", "name": "Local", "url": "http://127.0.0.1:8905/api/v1/health"})

    return agents


def _fetch(url: str) -> Optional[dict]:
    """Fetch health endpoint. Returns None if unreachable."""
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "hermes-fleet-watchdog/1.0"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


def _fingerprint(data: Optional[dict]) -> str:
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


def _check_workflows() -> dict:
    """Check for active workflow steps via Agent Bus messages.

    Returns {
        "active_count": int,
        "stalled": [{"agent": str, "step": str, "running_for_min": int}]
    }
    """
    active = 0
    stalled = []
    now = time.time()

    if not INBOX_DIR.exists():
        return {"active_count": 0, "stalled": []}

    for f in sorted(os.listdir(str(INBOX_DIR)))[-50:]:
        path = INBOX_DIR / f
        if not path.is_file() or not f.endswith(".md"):
            continue
        try:
            content = path.read_text()
            # Look for workflow_step messages
            if "workflow_step" in content and "human_review: true" not in content:
                active += 1
                # Extract agent name from path or content
                agent = "unknown"
                m = re.search(r"to:\s*(\w+)", content)
                if m:
                    agent = m.group(1)
                # Check age
                try:
                    age = now - path.stat().st_mtime
                    if age > 300:  # 5 min
                        stalled.append({"agent": agent, "step": f[:20], "running_for_min": int(age / 60)})
                except OSError:
                    print("expected — silently handled", file=sys.stderr)
        except (OSError, UnicodeDecodeError):
            continue

    return {"active_count": active, "stalled": stalled}


def main():
    agents = _get_agents()

    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled

    now: dict[str, str] = {}
    alerts: list[str] = []
    resolves: list[str] = []
    poll_results: dict[str, Optional[dict]] = {}

    for a in agents:
        key = a["key"]
        name = a["name"]
        data = _fetch(a["url"])
        poll_results[key] = data
        fp = _fingerprint(data)
        now[key] = fp
        old = prev.get(key, "")

        if fp == old:
            continue

        if data is None:
            alerts.append(f"🔴 {name} — unreachable")
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

    # Workflow check
    wf = _check_workflows()
    dashboard = {
        "agents": {},
        "workflows": wf,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    for a in agents:
        key = a["key"]
        data = poll_results.get(key)
        if data is None:
            dashboard["agents"][key] = {"status": "🌙 offline", "healthy": False}
        elif not data.get("healthy", True):
            dashboard["agents"][key] = {"status": "🔴 unhealthy", "healthy": False, "issues": len(data.get("issues", []))}
        else:
            dashboard["agents"][key] = {"status": "✅ active", "healthy": True}

    if wf["active_count"] > 0:
        dashboard["workflow_summary"] = f"{wf['active_count']} active"
        if wf["stalled"]:
            for s in wf["stalled"]:
                alerts.append(f"⏳ Stalled: {s['agent']} — {s['step']} ({s['running_for_min']}m)")

    # Save dashboard data
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(json.dumps(dashboard, indent=2))

    # Save fingerprint state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(now, indent=2))

    # Output — no_agent cron delivers non-empty stdout
    output = []
    ts = format_timestamp("%Y-%m-%d %H:%M %Z")
    if alerts:
        output.append(f"━━━ Fleet Watchdog — {len(alerts)} issue(s) ━━━ [{ts}]")
        output.extend(alerts)
    if resolves:
        output.append(f"━━━ Health Restored ━━━ [{ts}]")
        output.extend(resolves)

    if output:
        print("\n\n".join(output))


if __name__ == "__main__":
    main()
