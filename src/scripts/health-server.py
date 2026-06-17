#!/usr/bin/env python3
"""health-server.py — Universal health API for Hermes Cortex agents.

Single-file FastAPI server exposing a consistent /api/v1/health endpoint.
Same schema on every machine — Moses polls all agents for consolidated health.

Usage:
    python3 health-server.py --server moses
    # → http://127.0.0.1:8905/api/v1/health

Endpoints:
    GET /api/v1/health    — Consolidated system health (the canonical endpoint)
    GET /api/v1/health/resources  — CPU / memory / disk
    GET /api/v1/health/services   — Service status
    GET /health           — Backward-compat alias for /api/v1/health

Security:
    Behind nginx with basic auth + rate limiting (see nginx config template).
    No secrets in this file — auth is at the proxy layer.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ImportError:
    print("ERROR: Requires fastapi + uvicorn. Install: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────
SERVER_NAME = os.environ.get("HEALTH_SERVER_NAME", platform.node().split(".")[0])
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8905"))
HOME = Path.home()

# Startup timestamp for uptime tracking
_STARTUP_TS = time.time()

app = FastAPI(title=f"Health Server — {SERVER_NAME}", version="1.0.0")


# ── Helpers ────────────────────────────────────────────────────
def _run(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    """Run a command, return (stdout, stderr, rc)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def _get_uptime() -> int:
    return int(time.time() - _STARTUP_TS)


def _get_os() -> str:
    return f"{platform.system().lower()}/{platform.release()}"


# ── Resource checks ────────────────────────────────────────────
def _check_resources() -> dict:
    """Gather CPU, memory, disk metrics."""
    issues: list[dict] = []
    data: dict = {}

    # CPU
    if sys.platform == "darwin":
        out, _, _ = _run(["ps", "-A", "-o", "%cpu="])
        cpus = [float(x) for x in out.split() if x.replace(".", "").isdigit()]
        data["cpu_percent"] = round(sum(cpus), 1) if cpus else 0.0
        # Load avg
        data["load_avg"] = [round(x, 2) for x in os.getloadavg()]
    elif sys.platform == "linux":
        out, _, _ = _run(["cat", "/proc/loadavg"])
        parts = out.split()
        data["load_avg"] = [float(parts[0]), float(parts[1]), float(parts[2])] if len(parts) >= 3 else []
        # Parse /proc/stat for CPU percentage (more reliable than top piping)
        stat_out, _, _ = _run(["cat", "/proc/stat"])
        for line in stat_out.split("\n"):
            if line.startswith("cpu "):
                vals = [int(x) for x in line.split()[1:]]
                if vals:
                    total = sum(vals)
                    idle = vals[3]  # idle column
                    data["cpu_percent"] = round(100 * (1 - idle / total), 1) if total else 0.0
                break

    # Memory
    if sys.platform == "darwin":
        out, _, rc = _run(["memory_pressure"])
        if rc == 0:
            for line in out.split("\n"):
                if "System-wide memory" in line and "%" in line:
                    import re
                    m = re.search(r'(\d+)%', line)
                    if m:
                        free_pct = int(m.group(1))
                        data["memory_free_percent"] = free_pct
                        data["memory_percent"] = 100 - free_pct
                    break
    elif sys.platform == "linux":
        out, _, _ = _run(["free", "-m"])
        for line in out.split("\n"):
            if line.startswith("Mem:"):
                parts = line.split()
                total = int(parts[1])
                available = int(parts[6])
                data["memory_percent"] = round(100 * (1 - available / total), 1)
                data["memory_free_percent"] = round(100 * available / total, 1)
                break

    # Disk
    if sys.platform in ("darwin", "linux"):
        out, _, rc = _run(["df", "-h", "/"])
        if rc == 0:
            lines = out.split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                for p in parts:
                    if p.endswith("%"):
                        data["disk_percent"] = int(p.rstrip("%"))
                        break
                if len(parts) >= 2:
                    data["disk_total"] = parts[1] if len(parts) > 1 else ""
                    data["disk_used"] = parts[2] if len(parts) > 2 else ""
                    data["disk_avail"] = parts[3] if len(parts) > 3 else ""

    # Health
    healthy = True
    dp = data.get("disk_percent", 0)
    mp = data.get("memory_percent", 0)
    if dp and dp > 90:
        issues.append({"severity": "critical", "check": "resources", "detail": f"Disk at {dp}%", "metric": "disk_percent", "value": dp, "threshold": 90})
        healthy = False
    elif dp and dp > 80:
        issues.append({"severity": "warning", "check": "resources", "detail": f"Disk at {dp}%", "metric": "disk_percent", "value": dp, "threshold": 80})
    if mp and mp > 90:
        issues.append({"severity": "critical", "check": "resources", "detail": f"Memory at {mp}%", "metric": "memory_percent", "value": mp, "threshold": 90})
        healthy = False
    elif mp and mp > 80:
        issues.append({"severity": "warning", "check": "resources", "detail": f"Memory at {mp}%", "metric": "memory_percent", "value": mp, "threshold": 80})

    return {"healthy": healthy, "issues": issues, "data": data}


# ── Service checks ────────────────────────────────────────────
def _check_services() -> dict:
    """Check critical services."""
    issues: list[dict] = []
    items: list[dict] = []
    healthy = True

    services: list[dict] = []

    if sys.platform == "darwin":
        services = [
            {"name": "nginx", "launchctl": None, "pgrep": "nginx: master"},
            {"name": "ollama", "launchctl": "com.ollama.serve", "pgrep": None},
            {"name": "gbrain", "launchctl": "com.gbrain.autopilot", "pgrep": None},
        ]
        # Check agent-inbox server
        inbox_pid_file = HOME / ".hermes" / "agent-inbox" / "server.pid"
        services.append({"name": "agent_inbox", "launchctl": "com.hermes.agent-inbox", "pgrep": None})
    elif sys.platform == "linux":
        services = [
            {"name": "nginx", "launchctl": None, "pgrep": "nginx: master"},
            {"name": "ollama", "launchctl": None, "pgrep": "ollama"},
            {"name": "gbrain", "launchctl": None, "pgrep": "gbrain"},
        ]

    for svc in services:
        status = "unknown"
        pid = None

        # Check via launchctl (macOS)
        if svc.get("launchctl"):
            out, _, rc = _run(["launchctl", "list", svc["launchctl"]])
            if rc == 0 and out:
                # macOS 12 outputs plist-style dict; newer macOS outputs tabular
                pid_match = None
                import re
                m = re.search(r'\"PID\"\s*=\s*(\d+)', out)
                if m:
                    pid_match = m.group(1)
                if pid_match:
                    pid = int(pid_match)
                    status = "running"
                else:
                    # Fallback: check if it says "PID" = 0 or missing
                    status = "stopped"
                    healthy = False
            else:
                status = "stopped"
                healthy = False

        # Fallback: check via pgrep
        if status == "unknown" and svc.get("pgrep"):
            out, _, _ = _run(["pgrep", "-f", svc["pgrep"]])
            if out:
                pids = out.split()
                pid = int(pids[0]) if pids else None
                status = "running"
            else:
                status = "stopped"
                healthy = False

        entry = {"name": svc["name"], "status": status, "pid": pid}
        items.append(entry)
        if status == "stopped":
            issues.append({"severity": "critical", "check": "services", "detail": f"{svc['name']} is not running", "service": svc["name"]})

    return {"healthy": healthy, "issues": issues, "items": items}


# ── Cron health check ─────────────────────────────────────────
def _check_cron_health() -> dict:
    """Check cached cron job health from jobs.json."""
    issues: list[dict] = []
    healthy = True
    jobs_json = HOME / ".hermes" / "cron" / "jobs.json"

    errored: list[str] = []
    stale: list[str] = []
    total = 0

    if jobs_json.exists():
        try:
            data = json.loads(jobs_json.read_text())
            job_list = data if isinstance(data, list) else data.get("jobs", [])
            total = len(job_list)
            now = time.time()
            for j in job_list:
                status = j.get("last_status", "")
                if status == "error":
                    errored.append(j.get("name", j.get("job_id", "unknown")))
                    healthy = False
                # Check for stale jobs (not run in > 2x their schedule)
                last_run = j.get("last_run_at")
                if last_run and "T" in str(last_run):
                    try:
                        last = datetime.fromisoformat(str(last_run)).timestamp()
                        elapsed = now - last
                        # Estimate schedule interval
                        sched = j.get("schedule", "")
                        if sched and elapsed > 86400:  # > 24h since last run
                            stale.append(j.get("name", j.get("job_id", "unknown")))
                    except (ValueError, TypeError):
                        pass
        except (json.JSONDecodeError, KeyError):
            pass

    for e in errored:
        issues.append({"severity": "high", "check": "cron_health", "detail": f"Errored cron: {e}", "cron": e})
    for s in stale:
        issues.append({"severity": "warning", "check": "cron_health", "detail": f"Stale cron (no recent run): {s}", "cron": s})

    return {
        "healthy": healthy,
        "issues": issues,
        "total_jobs": total,
        "errored": errored,
        "stale": stale,
    }


# ── Consolidated health ───────────────────────────────────────
def _build_health() -> dict:
    """Build the full consolidated health response."""
    checks = {}
    all_issues: list[dict] = []
    healthy = True

    for name, fn in [("resources", _check_resources), ("services", _check_services), ("cron_health", _check_cron_health)]:
        result = fn()
        checks[name] = {
            "healthy": result["healthy"],
            **({k: v for k, v in result.items() if k not in ("healthy", "issues")}),
        }
        if not result["healthy"]:
            healthy = False
        all_issues.extend(result.get("issues", []))

    # Sort issues by severity
    severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 99))

    return {
        "server": SERVER_NAME,
        "hostname": platform.node().split(".")[0],
        "platform": _get_os(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": _get_uptime(),
        "healthy": healthy,
        "checks": checks,
        "issues": all_issues,
    }


# ── Routes ────────────────────────────────────────────────────
@app.get("/api/v1/health")
async def health_v1():
    return _build_health()


@app.get("/api/v1/health/resources")
async def health_resources():
    result = _check_resources()
    return {"server": SERVER_NAME, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/api/v1/health/services")
async def health_services():
    result = _check_services()
    return {"server": SERVER_NAME, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/health")
async def health_legacy():
    """Backward-compat alias for /api/v1/health."""
    return _build_health()


@app.get("/")
async def index():
    return {
        "service": f"Health Server — {SERVER_NAME}",
        "version": "1.0.0",
        "endpoints": {
            "/api/v1/health": "Consolidated system health",
            "/api/v1/health/resources": "CPU, memory, disk",
            "/api/v1/health/services": "Service status",
            "/health": "Alias for /api/v1/health",
        },
    }


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=HEALTH_PORT, log_level="info")