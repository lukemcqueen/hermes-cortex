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

Agent registry at ~/.hermes/state/agent-registry.json — each agent
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
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
from hermes_tz import format_timestamp

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "health-state.json"
HEALTH_DATA_FILE = HOME / ".hermes" / "state" / "agent-health-data.json"
REGISTRY_PATH = HOME / ".hermes" / "state" / "agent-registry.json"
REGISTRY_TEMPLATE = HOME / "hermes-cortex" / "src" / "agent-registry.template.json"
REGISTRY_LOCAL = HOME / ".hermes" / "agent-registry.local.json"
CORTEX_ENV = HOME / "hermes-cortex" / ".env"
TIMEOUT = 5
HEALTH_TOPIC = "health"

SERVICE_MAP = [
    "resources", "services", "no_errored_crons", "no_stale_crons",
    "nginx", "ollama", "gbrain", "disk_ok", "gbrain_sources_ok",
]

SERVICE_ICONS = {1: "✅", 0: "➖", -1: "❌"}
SEVERITY_MAP = {-1: "critical", 0: "info"}


# ── Inbox connection (from hermes-inbox.conf) ──

def _load_inbox_config() -> dict:
    """Load inbox URL and auth from env vars, fallback to hermes-cortex/.env."""
    config = {"url": "", "auth": ""}

    # Try environment variables first
    env_url = os.environ.get("CORTEX_INBOX_URL", "")
    env_auth = os.environ.get("CORTEX_INBOX_AUTH", "")
    if env_url:
        config["url"] = env_url.rstrip("/")
    if env_auth:
        config["auth"] = env_auth

    # Fallback: parse from hermes-cortex/.env
    if not config["url"] and CORTEX_ENV.exists():
        for line in CORTEX_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k == "CORTEX_INBOX_URL" and not config["url"]:
                config["url"] = v.rstrip("/")
            elif k == "CORTEX_INBOX_AUTH" and not config["auth"]:
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
    if not registry and REGISTRY_TEMPLATE.exists():
        try:
            registry = json.loads(REGISTRY_TEMPLATE.read_text())
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
            "method": "http", "url": "http://127.0.0.1:13007/",
        })
    return agents


# ── Fetching ──

def _fetch_http(url: str, auth: str = "") -> dict | None:
    """HTTP GET to a health-vector endpoint. Supports Basic Auth.
    
    Retries once on failure to tolerate transient network blips.
    """
    import base64
    headers = {"Accept": "application/json", "User-Agent": "hermes-health-monitor/1.0"}
    if auth:
        encoded = base64.b64encode(auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    for attempt in range(2):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
            if attempt == 0:
                time.sleep(1)  # brief pause before retry
                continue
            return None
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
      - Rich health-report JSON: {"type": "health-report", "healthy": true,
        "services": [...], "issues": [...], ...}  (Titus format)
    """
    if not body:
        return None

    # Try JSON first
    if body.startswith("{"):
        try:
            parsed = json.loads(body)
            if "v" in parsed and isinstance(parsed["v"], list):
                return parsed
            # Check for Titus' rich health-report format
            if parsed.get("type") == "health-report":
                return _parse_rich_report(parsed)
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


def _parse_rich_report(report: dict) -> dict:
    """Convert Titus' rich health-report JSON to compact vector format,
    preserving extra metadata for the dashboard.

    Maps Titus' services + issues to the SERVICE_MAP vector:
      0 resources, 1 services, 2 no_errored_crons, 3 no_stale_crons,
      4 nginx, 5 ollama, 6 gbrain, 7 disk_ok, 8 gbrain_sources_ok
    """
    service_map = SERVICE_MAP
    vec = [0] * len(service_map)

    # Index 0: resources — 1 if resources data present
    resources = report.get("resources", {})
    vec[0] = 1 if resources else 0

    # Index 1: services — 1 if service list present
    services = report.get("services", [])
    vec[1] = 1 if services else 0

    # Map reported services by name to indices 4-6
    svc_by_name = {}
    for s in services:
        svc_by_name[s.get("name", "").lower()] = s.get("status", "")

    for idx, svc_name in enumerate(service_map):
        if svc_name in svc_by_name:
            status = svc_by_name[svc_name].lower()
            vec[idx] = 1 if status in ("running", "up") else -1 if status in ("down", "stopped") else 0

    # Check issues for cron health
    issues = report.get("issues", [])
    has_errored = False
    has_stale = False
    for iss in issues:
        check = iss.get("check", "").lower()
        detail = iss.get("detail", "").lower()
        if "errored" in detail or check == "cron_health" and "errored" in detail:
            has_errored = True
        if "stale" in detail:
            has_stale = True

    # Index 2: no_errored_crons
    vec[2] = -1 if has_errored else 1
    # Index 3: no_stale_crons
    vec[3] = -1 if has_stale else 1

    # Index 7: disk_ok
    disk_pct = resources.get("disk_percent", 0)
    vec[7] = -1 if (disk_pct and disk_pct >= 90) else 1 if disk_pct else 0

    # Index 8: gbrain_sources_ok — default 1 if gbrain is running
    vec[8] = 1 if svc_by_name.get("gbrain", "") in ("running", "up") else 0

    hostname = report.get("hostname") or report.get("agent") or report.get("server", "unknown")

    result = {
        "v": vec,
        "h": hostname,
        "t": int(time.time()),
    }
    # Preserve rich metadata for dashboard enrichment
    result["_rich"] = {
        "issues": report.get("issues", []),
        "services_raw": services,
        "resources": resources,
        "uptime_seconds": report.get("uptime_seconds"),
        "service_summary": report.get("service_summary", ""),
        "issue_count": report.get("issue_count", len(report.get("issues", []))),
        "critical_count": report.get("critical_count", 0),
    }
    return result


# ── Health data conversion ──

def _vector_to_health_data(vec: list[int], hostname: str, name: str) -> dict:
    """Convert health-vector format to Dashboard-compatible health dict.
    
    Severity mapping for -1 values:
      Indices 0 (resources), 2 (no_errored_crons), 3 (no_stale_crons),
      8 (gbrain_sources_ok) → 'warning' (yellow in dashboard)
      Indices 1 (services), 4 (nginx), 5 (ollama), 6 (gbrain), 7 (disk_ok)
      → 'critical' (red in dashboard)
    """
    WARNING_INDICES = {0, 2, 3, 8}  # moderate issues → yellow
    issues = []
    services = []
    all_ok = True
    critical_count = 0

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
            severity = "warning" if i in WARNING_INDICES else "critical"
            if severity == "critical":
                critical_count += 1
            issues.append({
                "severity": severity,
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
        "critical_count": critical_count,
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
    """Build structured health snapshot for dashboard consumption.
    Uses rich metadata from agents that provide it (Titus format)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    health_data = {}

    for key, result in poll_results.items():
        vec = result.get("vector")
        error = result.get("error")
        name = result.get("name", key.capitalize())
        hostname = result.get("hostname", "")
        rich = result.get("_rich")

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
                "hostname": hostname,
            }
        elif rich:
            # Use rich metadata from Titus-style health-report
            svc_items = []
            for s in rich.get("services_raw", []):
                svc_items.append({
                    "name": s.get("name", "?"),
                    "status": s.get("status", "unknown"),
                    "pid": s.get("pid"),
                })
            issues_out = []
            for iss in rich.get("issues", []):
                issues_out.append({
                    "severity": iss.get("severity", "info"),
                    "check": iss.get("check", ""),
                    "detail": iss.get("detail", ""),
                })
            healthy = (rich.get("issue_count", 0) == 0
                       and vec is not None
                       and -1 not in vec)

            entry = _vector_to_health_data(vec, hostname, name)
            # Override with rich data
            entry["healthy"] = healthy
            entry["reachable"] = True
            entry["issues"] = issues_out
            entry["issue_count"] = len(issues_out)
            entry["critical_count"] = rich.get("critical_count", 0)
            if svc_items:
                up = sum(1 for s in svc_items if s["status"] in ("running", "up"))
                entry["services"] = {"items": svc_items, "up": up, "total": len(svc_items)}
                entry["service_summary"] = rich.get("service_summary", f"{up}/{len(svc_items)} up")
            entry["resources"] = rich.get("resources", {})
            if rich.get("uptime_seconds"):
                entry["uptime_seconds"] = rich["uptime_seconds"]
            health_data[key] = entry
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
            "_rich": data.get("_rich") if data else None,
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