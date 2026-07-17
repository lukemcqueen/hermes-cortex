#!/usr/bin/env python3
"""report-agent-health.py — Push-based health reporter for unreachable agents.

no_agent watchdog pattern:
  Empty stdout → silent (healthy, no change since last report)
  Text output  → delivered (health issues or state changes)

Reads dashboard health at http://127.0.0.1:8901/api/health
and POSTs the structured result to Moses's agent inbox for
dashboard consumption. ALSO checks the external health URL
(Principle #14 — never report healthy from localhost alone).

Reads dashboard health at http://127.0.0.1:8901/api/health
and POSTs the structured result to Moses's agent inbox for
dashboard consumption.

Configuration (env vars or ~/.hermes-cortex/cortex-bus.conf):
  CORTEX_BUS_FALLBACK_URL     — Moses inbox MCP endpoint (POST via internal API)
  CORTEX_BUS_FALLBACK_AUTH    — "user:pass" for Basic Auth
  AGENT_NAME           — name to report as (default: hostname)
  EXTERNAL_HEALTH_URL  — external URL to verify reachability (Principle #14)

Cron setup on the remote agent:
  cronjob action=create schedule="every 10m" \
    name=report-agent-health \
    prompt="..." \
    no_agent=true \
    script=report-agent-health.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Optional

HOME = Path.home()
CONFIG_FILE = HOME / ".hermes" / "cortex-bus.conf"
HEALTH_LOCAL = 'http://127.0.0.1:8901/api/health'
STATE_FILE = HOME / ".hermes-cortex" / "state" / "agent-health-push-state.json"
TIMEOUT = 15

# ── Config ────────────────────────────────────────────────────

# Load from config file first
inbox_url = os.environ.get("CORTEX_BUS_URL", "") or os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or os.environ.get("CORTEX_INBOX_URL", "")
inbox_auth = os.environ.get("CORTEX_BASIC_AUTH", "") or os.environ.get("CORTEX_BUS_AUTH", "") or os.environ.get("CORTEX_INBOX_AUTH", "")
bus_token = os.environ.get("CORTEX_BUS_TOKEN", "")
agent_name = os.environ.get("AGENT_NAME", "")
external_health_url = os.environ.get("EXTERNAL_HEALTH_URL", "")

if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k == "CORTEX_BUS_URL" and not inbox_url:
                        inbox_url = v
                    elif k == "CORTEX_BUS_FALLBACK_URL" and not inbox_url:
                        inbox_url = v
                    elif k == "CORTEX_INBOX_URL" and not inbox_url:
                        inbox_url = v
                    elif k == "CORTEX_BASIC_AUTH" and not inbox_auth:
                        inbox_auth = v
                    elif k == "CORTEX_BUS_TOKEN" and not bus_token:
                        bus_token = v
                    elif k == "EXTERNAL_HEALTH_URL" and not external_health_url:
                        external_health_url = v
    except Exception:
        pass

if not agent_name:
    import platform
    agent_name = platform.node().split(".")[0]

if not inbox_url:
    print("ERROR: CORTEX_BUS_FALLBACK_URL (or CORTEX_INBOX_URL) not set", file=sys.stderr)
    sys.exit(1)


# ── Fetch local health ─────────────────────────────────────────

def fetch_local_health() -> Optional[dict]:
    """Fetch from local health server."""
    try:
        req = Request(HEALTH_LOCAL, headers={"Accept": "application/json", "User-Agent": "hermes-health-reporter/1.0"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"healthy": False, "error": str(e), "server": agent_name}


# ── External reachability check (Principle #14) ────────────────

def check_external_reachability() -> dict:
    """Test TCP connectivity to the external health URL.

    Returns dict with reachable, url_tested, detail fields.
    Used to verify the health endpoint is externally accessible,
    not just locally running.
    """
    result = {
        "reachable": False,
        "url_tested": external_health_url or "(not configured)",
        "detail": "",
    }
    if not external_health_url:
        result["detail"] = "EXTERNAL_HEALTH_URL not configured — skipping external check"
        return result

    try:
        from urllib.parse import urlparse
        parsed = urlparse(external_health_url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 443

        # Test TCP connectivity — validates DNS + firewall + service listening
        addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        result["reachable"] = True
        result["detail"] = f"TCP connected to {host}:{port}"
    except socket.gaierror as e:
        result["detail"] = f"DNS resolution failed: {e}"
    except (socket.timeout, OSError) as e:
        result["detail"] = f"TCP connection failed: {e}"

    return result


# ── Fingerprint ────────────────────────────────────────────────

def fingerprint(data: Optional[dict]) -> str:
    """Stable fingerprint for change detection."""
    if data is None:
        return "unreachable"
    parts = [f"ok={data.get('healthy', False)}"]
    for iss in data.get("issues", []):
        parts.append(f"{iss.get('check')}:{iss.get('severity')}:{iss.get('detail')}")
    return "|".join(parts)


# ── Build health report ────────────────────────────────────────

def build_report(data: Optional[dict]) -> dict:
    """Build the health report payload for Moses inbox."""
    now_iso = datetime.now(timezone.utc).isoformat()

    if data is None:
        return {
            "type": "health-report",
            "agent": agent_name,
            "healthy": False,
            "reachable": False,
            "timestamp": now_iso,
            "issues": [{"severity": "critical", "detail": "Health server unreachable locally"}],
        }

    services = ((data.get("checks") or {}).get("services") or {}).get("items", [])
    issues = list(data.get("issues", []))

    # The health endpoint is the Cortex dashboard (:8901) which uses "overall"
    # instead of the health-server "healthy" field. Accept both.
    is_healthy = data.get("healthy") or (data.get("overall") == "healthy")

    # ── Check external reachability (Principle #14) ──
    ext = check_external_reachability()
    external_reachable = ext.get("reachable", False)
    if external_health_url and not external_reachable:
        is_healthy = False
        issues.append({
            "severity": "critical" if issues else "warning",
            "check": "external_reachability",
            "detail": ext.get("detail", "External health URL unreachable"),
        })
    elif external_health_url and external_reachable:
        issues.append({
            "severity": "info",
            "check": "external_reachability",
            "detail": ext.get("detail", "External health URL reachable"),
        })

    return {
        "type": "health-report",
        "agent": agent_name,
        "healthy": is_healthy,
        "reachable": True,
        "server": data.get("server", agent_name),
        "hostname": data.get("hostname", agent_name),
        "timestamp": now_iso,
        "issues": issues,
        "issue_count": len([i for i in issues if i.get("severity") in ("critical", "high", "warning")]),
        "critical_count": sum(1 for i in issues if i.get("severity") == "critical"),
        "services": services,
        "service_summary": f"{sum(1 for s in services if s.get('status') == 'running')}/{len(services)} up",
        "uptime_seconds": data.get("uptime_seconds", 0),
        "resources": data.get("checks", {}).get("resources", {}).get("data", {}),
        "external_reachability": ext,
    }


# ── Send to Moses inbox ────────────────────────────────────────

def send_report(report: dict) -> bool:
    """POST health report to Moses via PGMQ Agent Bus."""
    try:
        import base64
        api_url = inbox_url.rstrip("/") + "/api/pgmq/send"

        # Auth: localhost → Bearer, remote → Basic
        host = api_url.split("://")[-1].split("/")[0].split(":")[0]
        auth_header = ""
        if host in ("127.0.0.1", "localhost", "::1"):
            if bus_token:
                auth_header = f"Bearer {bus_token}"
        else:
            if inbox_auth and ":" in inbox_auth:
                auth_header = f"Basic {base64.b64encode(inbox_auth.encode()).decode()}"

        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        payload = {
            "queue": "inbox_moses",
            "message": {
                "from": agent_name,
                "topic": "health",
                "subject": f"health-report {report.get('agent', 'unknown')} — {'healthy' if report.get('healthy', False) else 'issues'}",
                "body": json.dumps(report, indent=2),
            },
        }

        req = Request(
            api_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        body = ""
        if hasattr(e, 'read'):
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
        print(f"ERROR: Failed to send report: {e} {body}", file=sys.stderr)
        return False


# ── Main ────────────────────────────────────────────────────────

def main():
    # Fetch health
    data = fetch_local_health()
    fp = fingerprint(data)

    # Load previous state
    prev_fp = ""
    if STATE_FILE.exists():
        try:
            prev_fp = json.loads(STATE_FILE.read_text()).get("fingerprint", "")
        except Exception:
            pass

    # Build report (includes external reachability check)
    report = build_report(data)

    if fp == prev_fp and data and data.get("healthy", False):
        # No change and healthy — silent exit (watchdog pattern)
        return

    # Send report
    ok = send_report(report)
    if ok:
        # Save state
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"fingerprint": fp, "last_sent": datetime.now(timezone.utc).isoformat()}, indent=2))

        # Output for logging
        status = "healthy" if report["healthy"] else f"unhealthy ({report['issue_count']} issues)"
        ext_status = "ext=ok" if report.get("external_reachability", {}).get("reachable") else "ext=unchecked"
        print(f"Reported {agent_name} health: {status} {ext_status}")


if __name__ == "__main__":
    main()
