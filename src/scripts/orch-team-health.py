#!/usr/bin/env python3
"""orch-team-health.py — Cross-server health poller for Moses.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (new issues or resolutions)

State tracked in ~/.hermes/state/health-state.json — fingerprints
per agent so alerts only fire on state transitions.

Structured health data written to ~/.hermes/state/agent-health-data.json
for dashboard consumption — updated every poll cycle.

Two health methods:
  - http:   Poll agent's health-vector HTTP endpoint (server agents)
  - inbox:  Read agent's latest health push from the inbox (client-only agents)

Agent registry at ~/hermes-cortex/src/agent-registry.json — each agent
entry must set health_method to "http" or "inbox".
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

# ── Paths ──
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from hermes_tz import format_timestamp

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "health-state.json"
HEALTH_DATA_FILE = HOME / ".hermes" / "state" / "agent-health-data.json"
REGISTRY_PATH = HOME / "hermes-cortex" / "src" / "agent-registry.json"
REGISTRY_LOCAL = HOME / ".hermes" / "agent-registry.local.json"
INBOX_CONF = HOME / ".hermes" / "moses-inbox.conf"
TIMEOUT = 3
HEALTH_TOPIC = "health"

SERVICE_MAP = [
    "nginx", "ollama", "gbrain", "cortex-dashboard",
    "langfuse-web", "langfuse-worker", "docker", "hermes-gateway",
]

SERVICE_ICONS = {1: "✅", 0: "➖", -1: "❌"}
SEVERITY_MAP = {-1: "critical", 0: "info"}


# ── Inbox connection (from moses-inbox.conf) ──

def _load_inbox_config() -> dict:
    """Load inbox URL and auth from moses-inbox.conf."""
    config = {"url": "", "auth": ""}
    if not INBOX_CONF.exists():
        return config
    for line in INBOX_CONF.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'\"")
        if k == "MOSES_INBOX_URL":
            config["url"] = v.rstrip("/")
        elif k == "MOSES_INBOX_AUTH":
            config["auth"] = v
    return config


INBOX_CFG = _load_inbox_config()


def _inbox_request(path: str) -> dict | None:
    """Make an authenticated GET to the inbox API. Returns parsed JSON or None."""
    if not INBOX_CFG["url"]:
        return None

    url = f"{INBOX_CFG['url']}/{path.lstrip('/')}"
    headers = {"Accept": "application/json"}
    if INBOX_CFG["auth"]:
        encoded = base64.b64encode(INBOX_CFG["auth"].encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError):
        return None


# ── Agent loading ──

def _get_agents() -> list[dict]:
    """Load all tracked agents from registry — HTTP-pollable and inbox-based.

    Merges local overrides from ~/.hermes/agent-registry.local.json on top of
    the main registry. Local overrides can set health_url, accessible, etc.
    without committing to the public repo.
    """
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
        # Apply local overrides
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
                agents.append({
                    "key": key, "name": name,
                    "method": "http", "url": url,
                })
        elif method == "inbox":
            agents.append({
                "key": key, "name": name,
                "method": "inbox",
            })

    # Fallback: always include Moses local health if not already present
    if not any(a["key"] == "moses" for a in agents):
        agents.insert(0, {
            "key": "moses", "name": "Moses",
            "method": "http", "url": "http://127.0.0.1:13006/",
        })
    return agents


# ── Fetching ──

def _fetch_http(url: str, auth: str = "") -> dict | None:
    """HTTP GET to a health-vector endpoint. Supports Basic Auth."""
    import base64
    headers = {"Accept": "application/json", "User-Agent": "hermes-health-monitor/1.0"}
    if auth:
        encoded = base64.b64encode(auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        return None


def _fetch_inbox(agent_key: str) -> dict | None:
    """Read the latest health push from the inbox for a given agent.

    Looks for the most recent message on the 'health' topic from this agent
    and parses the body as a health vector.
    """
    data = _inbox_request(f"api/inbox?limit=10&topic={HEALTH_TOPIC}")
    if not data:
        return None

    msgs = data.get("messages", [])
    # Find most recent message from this agent
    for msg in msgs:
        if msg.get("from", "").lower() == agent_key.lower():
            body = msg.get("body", "").strip()
            return _parse_vector_body(body)

    return None


def _parse_vector_body(body: str) -> dict | None:
    """Parse a health vector from a message body.

    Accepts:
      - Raw parentheses string: (1 1 0 1 -1 1 1 1)
      - Compact JSON: {"v": [1,1,0,...], "h": "hostname", "t": 1234}
      - Full JSON: any format with "v" key
    """
    if not body:
        return None

    # Try JSON first
    if body.startswith("{"):
        try:
            parsed = json.loads(body)
            if "v" in parsed and isinstance(parsed["v"], list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try parenthesised format: (1 1 0 1 -1 1 1 1)
    m = re.match(r"^\(\s*([-\d\s]+)\s*\)$", body)
    if m:
        try:
            vec = [int(x) for x in m.group(1).split()]
            return {"v": vec, "h": "unknown", "t": int(time.time())}
        except ValueError:
            pass

    return None


# ── Health data conversion ──

def _vector_to_health_data(vec: list[int], hostname: str, name: str) -> dict:
    """Convert health-vector format to Dashboard-compatible health dict."""
    issues = []
    services = []
    all_ok = True

    for i, svc_name in enumerate(SERVICE_MAP):
        status = vec[i] if i < len(vec) else 0
        status_label = {1: "running", 0: "n/a", -1: "down"}.get(status, "unknown")
        services.append({
            "name": svc_name,
            "status": status_label,
            "index": i,
        })
        if status == -1:
            all_ok = False
            issues.append({
                "severity": "critical",
                "check": svc_name,
                "detail": f"{svc_name} is down",
            })

    up_count = sum(1 for s in services if s["status"] == "running")
    total = sum(1 for s in services if s["status"] in ("running", "down"))

    return {
        "healthy": all_ok,
        "server": name,
        "hostname": hostname,
        "vector": vec,
        "issues": issues,
        "issue_count": len(issues),
        "critical_count": len(issues),
        "services": {"items": services, "up": up_count, "total": total},
        "service_summary": f"{up_count}/{total} up",
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }


def _fingerprint(vector: list[int] | None) -> str:
    """Stable fingerprint from a health vector for change detection."""
    if vector is None:
        return "unreachable"
    return ",".join(str(v) for v in vector)


def _build_structured_data(poll_results: dict[str, dict]) -> dict:
    """Build structured health snapshot for dashboard consumption."""
    now_iso = datetime.now(timezone.utc).isoformat()
    health_data = {}

    for key, result in poll_results.items():
        vec = result.get("vector")
        error = result.get("error")
        name = result.get("name", key.capitalize())
        hostname = result.get("hostname", "")

        if vec is None:
            health_data[key] = {
                "healthy": False,
                "reachable": False,
                "server": name,
                "issues": [{
                    "severity": "critical",
                    "detail": "Unreachable",
                    "error": error or "timeout/connection failed",
                }],
                "services": [],
                "last_seen": now_iso,
            }
        else:
            hd = _vector_to_health_data(vec, hostname, name)
            hd["reachable"] = True
            health_data[key] = hd

    return health_data


# ── Main ──

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
    poll_results: dict[str, dict] = {}

    for a in agents:
        key = a["key"]
        name = a["name"]
        vector = None
        hostname = ""
        error = None

        if a["method"] == "http":
            data = _fetch_http(a["url"], auth=INBOX_CFG["auth"])
            if data and "v" in data:
                vector = data["v"]
                hostname = data.get("h", "")
            else:
                error = "unreachable" if data is None else "invalid format"
        elif a["method"] == "inbox":
            data = _fetch_inbox(key)
            if data and "v" in data:
                vector = data["v"]
                hostname = data.get("h", "")
            else:
                error = "no health message in inbox" if data is None else "invalid format"

        poll_results[key] = {
            "vector": vector, "error": error,
            "name": name, "hostname": hostname,
        }
        fp = _fingerprint(vector)
        now[key] = fp
        old = prev.get(key, "")

        if fp == old:
            continue  # No change

        if vector is None:
            alerts.append(f"🔴 {name} — {error or 'unreachable'}")
        else:
            # Check for down services
            down_indices = [i for i, v in enumerate(vector) if v == -1]
            if down_indices:
                lines = []
                for i in down_indices:
                    svc = SERVICE_MAP[i] if i < len(SERVICE_MAP) else f"service[{i}]"
                    lines.append(f"❌ {svc}")
                alerts.append(f"🔴 {name}\n" + "\n".join(lines))
            else:
                # Was down/unreachable, now healthy
                if old and old != fp and old != "unreachable" and ("-1" in old):
                    resolves.append(f"✅ {name} — all services restored")
                elif old == "unreachable" or (old and "ok=" not in old and name == moses_check(old)):
                    resolves.append(f"✅ {name} — back online")

    # Save fingerprint state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(now, indent=2))

    # Save structured health data
    health_data = _build_structured_data(poll_results)
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


def moses_check(old: str) -> bool:
    """Detect if old fingerprint was from Dashboard format (Moses fallback)."""
    return "ok=" in old


if __name__ == "__main__":
    main()