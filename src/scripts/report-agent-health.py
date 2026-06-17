#!/usr/bin/env python3
"""report-agent-health.py — Push-based health reporter for unreachable agents.

no_agent watchdog pattern:
  Empty stdout → silent (healthy, no change since last report)
  Text output  → delivered (health issues or state changes)

Reads local health-server.py at http://127.0.0.1:8905/api/v1/health
and POSTs the structured result to Moses's agent inbox for
dashboard consumption.

Moses reads these from the inbox and merges them into
agent-health-data.json.

Configuration (env vars or ~/.hermes/moses-inbox.conf):
  MOSES_INBOX_URL   — Moses inbox POST endpoint
  MOSES_INBOX_AUTH  — "user:pass" for Basic Auth
  AGENT_NAME        — name to report as (default: hostname)

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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOME = Path.home()
CONFIG_FILE = HOME / ".hermes" / "moses-inbox.conf"
HEALTH_LOCAL = "http://127.0.0.1:8905/api/v1/health"
STATE_FILE = HOME / ".hermes" / "state" / "agent-health-push-state.json"
TIMEOUT = 15

# ── Config ────────────────────────────────────────────────────

# Load from config file first
inbox_url = os.environ.get("MOSES_INBOX_URL", "")
inbox_auth = os.environ.get("MOSES_INBOX_AUTH", "")
agent_name = os.environ.get("AGENT_NAME", "")

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
                    if k == "MOSES_INBOX_URL" and not inbox_url:
                        inbox_url = v
                    elif k == "MOSES_INBOX_AUTH" and not inbox_auth:
                        inbox_auth = v
    except Exception:
        pass

if not agent_name:
    import platform
    agent_name = platform.node().split(".")[0]

if not inbox_url:
    print("ERROR: MOSES_INBOX_URL not set", file=sys.stderr)
    sys.exit(1)


# ── Fetch local health ─────────────────────────────────────────

def fetch_local_health() -> dict | None:
    """Fetch from local health server."""
    try:
        req = Request(HEALTH_LOCAL, headers={"Accept": "application/json", "User-Agent": "hermes-health-reporter/1.0"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"healthy": False, "error": str(e), "server": agent_name}


# ── Fingerprint ────────────────────────────────────────────────

def fingerprint(data: dict | None) -> str:
    """Stable fingerprint for change detection."""
    if data is None:
        return "unreachable"
    parts = [f"ok={data.get('healthy', False)}"]
    for iss in data.get("issues", []):
        parts.append(f"{iss.get('check')}:{iss.get('severity')}:{iss.get('detail')}")
    return "|".join(parts)


# ── Build health report ────────────────────────────────────────

def build_report(data: dict | None) -> dict:
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
    issues = data.get("issues", [])

    return {
        "type": "health-report",
        "agent": agent_name,
        "healthy": data.get("healthy", False),
        "reachable": True,
        "server": data.get("server", agent_name),
        "hostname": data.get("hostname", agent_name),
        "timestamp": now_iso,
        "issues": issues,
        "issue_count": len(issues),
        "critical_count": sum(1 for i in issues if i.get("severity") == "critical"),
        "services": services,
        "service_summary": f"{sum(1 for s in services if s.get('status') == 'running')}/{len(services)} up",
        "uptime_seconds": data.get("uptime_seconds", 0),
        "resources": data.get("checks", {}).get("resources", {}).get("data", {}),
    }


# ── Send to Moses inbox ────────────────────────────────────────

def send_report(report: dict) -> bool:
    """POST health report to Moses's agent inbox via form-encoded data."""
    try:
        import urllib.parse
        form_data = urllib.parse.urlencode({
            "from": "titus",
            "topic": "health",
            "subject": f"health-report {report.get('agent', 'unknown')} — {'healthy' if report.get('healthy', False) else 'issues'}",
            "body": json.dumps(report, indent=2),
        })
        req = Request(inbox_url, data=form_data.encode(), headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "hermes-health-reporter/1.0",
        })
        if inbox_auth:
            import base64
            auth = base64.b64encode(inbox_auth.encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status == 200
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        print(f"ERROR: Failed to send report: {e}", file=sys.stderr)
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

    # Build report
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
        print(f"Reported {agent_name} health: {status}")


if __name__ == "__main__":
    main()
