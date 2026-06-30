#!/usr/bin/env python3
"""orch-health-report.py — Live agent health snapshot for Telegram delivery.

no_agent watchdog pattern:
  Always outputs the snapshot (not silent) — this is a periodic report, not a state-change monitor.

Usage:
  python3 orch-health-report.py

Output:
  Compact markdown with emoji status per agent, one line per service.
  Designed for mobile Telegram display (narrow width, concise).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REGISTRY_PATH = HOME / "hermes-cortex" / "src" / "agent-registry.json"
REGISTRY_LOCAL = HOME / ".hermes" / "agent-registry.local.json"
TIMEOUT = 3
SERVICE_MAP = ["nginx", "ollama", "gbrain", "dash", "langfuse-w", "langfuse-b", "docker", "gateway"]
ICONS = {1: "🟢", 0: "⚪", -1: "🔴"}
STATUS_LABEL = {1: "✅", -1: "⚠️"}


def _get_agents() -> list[dict]:
    """Load agents from registry with local overrides, same as orch-team-health.py."""
    agents = []
    registry = {}
    local_overrides = {}

    if REGISTRY_PATH.exists():
        try:
            registry = json.loads(REGISTRY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    if REGISTRY_LOCAL.exists():
        try:
            local_overrides = json.loads(REGISTRY_LOCAL.read_text()).get("agents", {})
        except (json.JSONDecodeError, OSError):
            pass

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

    # Fallback: Moses local health
    if not any(a["key"] == "moses" for a in agents):
        agents.insert(0, {"key": "moses", "name": "Moses", "method": "http",
                          "url": "http://127.0.0.1:13007/health"})
    return agents


def _fetch(url: str) -> dict | None:
    """Fetch health vector from an agent."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "hermes-health-report/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def build_snapshot() -> str:
    """Build the health snapshot markdown string."""
    agents = _get_agents()
    ts = datetime.now(timezone.utc).strftime("%a %H:%M UTC")
    lines = [f"━━━ **Agent Health** — {ts} ━━━"]

    for agent in agents:
        key = agent["key"]
        name = agent["name"]

        if agent["method"] == "inbox":
            lines.append(f"\n**{name}** 📨 inbox push")
            continue

        data = _fetch(agent["url"])
        if not data or "v" not in data:
            lines.append(f"\n**{name}** 🔴 unreachable")
            continue

        vec = data["v"]
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
