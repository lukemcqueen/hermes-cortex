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
_raw_name = os.environ.get("HEALTH_SERVER_NAME", "auto")
if _raw_name == "auto" or not _raw_name:
    SERVER_NAME = platform.node().split(".")[0]
else:
    SERVER_NAME = _raw_name
AGENT_ID = os.environ.get("AGENT_ID", SERVER_NAME[0].lower() if SERVER_NAME else "?")
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
            {"name": "gbrain", "launchctl": "com.gbrain.autopilot", "pgrep": "gbrain"},
        ]
        # Check agent-inbox server
        inbox_pid_file = HOME / ".hermes-cortex" / "agent-inbox" / "server.pid"
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
                # If launchctl found the service but PID=0, service is registered but not running
            # If launchctl check failed, fall through to pgrep rather than marking stopped immediately

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
def _estimate_interval(schedule: str) -> int:
    """Estimate expected interval in seconds from a cron schedule.

    Uses the most significant constrained field to determine cadence:
    - Weekday or day-of-month constrained → weekly/monthly
    - Hour constrained (but no weekday) → daily
    - Only minute constrained → sub-hourly
    - Fallback: 86400 (24h)

    Stale check uses: elapsed > 2x expected.
    """
    if not schedule:
        return 86400
    s = schedule.strip()

    # 'every Nm' / 'every N min' / 'every Nh' format
    import re as _re
    m = _re.match(r'every\s+(\d+)\s*(m|min|h)', s, _re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return val * 60 if m.group(2) != 'h' else val * 3600

    # Standard 5-field cron
    parts = s.split()
    if len(parts) != 5:
        return 86400
    minute, hour, day, month, weekday = parts

    # Expand ranges (1-5 → 1,2,3,4,5) for weekday and day fields
    def _expand_range(field: str) -> list[int]:
        """Expand a cron field like '1-5' or '1,3-5' into a list of ints."""
        vals: list[int] = []
        for part in field.split(','):
            if '-' in part and part != '*':
                a, b = (int(x) for x in part.split('-', 1))
                vals.extend(range(a, b + 1))
            else:
                try:
                    vals.append(int(part))
                except ValueError:
                    pass
        return sorted(set(vals))

    # Check fields from most significant to least.
    # First matching constraint determines the cadence.

    # Day-of-month constrained → monthly
    if day not in ('*', '?'):
        return 30 * 86400

    # Weekday constrained → weekly (or multi-day gap based on schedule)
    if weekday not in ('*', '?'):
        dow_vals = _expand_range(weekday)
        if len(dow_vals) > 1:
            # Multi-day-per-week schedule: use the longest gap between days
            gaps = [(dow_vals[(i+1) % len(dow_vals)] - dow_vals[i]) % 7
                    for i in range(len(dow_vals))]
            max_gap = max(gaps)
            return max_gap * 86400
        return 7 * 86400  # single weekday = weekly

    # Hour constrained → daily cadence (or sub-daily based on hour pattern)
    if hour != '*':
        if ',' in hour:
            vals = sorted(int(x) for x in hour.split(','))
            min_gap = min(vals[i+1] - vals[i] for i in range(len(vals)-1))
            return min_gap * 3600
        elif '-' in hour:
            return 3600  # hourly within range
        elif hour.startswith('*/'):
            return int(hour[2:]) * 3600
        return 86400  # single hour = daily

    # Only minute constrained → sub-hourly
    if minute != '*':
        if ',' in minute:
            vals = sorted(int(x) for x in minute.split(','))
            min_gap = min(vals[i+1] - vals[i] for i in range(len(vals)-1)) if len(vals) > 1 else 1
            return max(min_gap * 60, 60)
        elif minute.startswith('*/'):
            return max(int(minute[2:]) * 60, 60)
        return 3600  # single minute = at most once per hour

    return 86400  # everything wildcarded = daily default


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
                # Check for stale jobs (not run in > 2x expected interval)
                last_run = j.get("last_run_at")
                if last_run and "T" in str(last_run):
                    try:
                        last = datetime.fromisoformat(str(last_run)).timestamp()
                        elapsed = now - last
                        sched = j.get("schedule", "")
                        if sched:
                            expected = _estimate_interval(sched)
                            if elapsed > 2 * expected and expected > 0:
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


# ── gbrain sources check ───────────────────────────────────────
_gbrain_cache: dict | None = None
_gbrain_cache_ts: float = 0
_GBRAIN_CACHE_TTL = 300  # 5 minutes

def _check_gbrain_sources() -> dict:
    """Check gbrain source health via gbrain doctor --json.

    Results are cached for 5 minutes to avoid blocking the health server
    with the 30s+ gbrain doctor subprocess call.

    Gracefully degrades when gbrain is unavailable:
      - Try 1: gbrain doctor --json (authoritative, 45s timeout)
      - Try 2: gbrain sources list (parseable fallback, 15s)
      - Returns UNKNOWN (not DOWN) when gbrain is unavailable
    """
    global _gbrain_cache, _gbrain_cache_ts
    now = time.time()
    if _gbrain_cache is not None and (now - _gbrain_cache_ts) < _GBRAIN_CACHE_TTL:
        return _gbrain_cache
    issues: list[dict] = []
    sources_ok = True

    def _run_gbrain(args, timeout=15):
        env = os.environ.copy()
        bun_bin = HOME / ".bun" / "bin"
        env["PATH"] = f"{bun_bin}:{env.get('PATH', '')}"
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
                env=env, cwd=str(HOME / "brain") if (HOME / "brain").exists() else None,
            )
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "", "timeout", -1
        except FileNotFoundError:
            return "", "command not found", -1
        except Exception as e:
            return "", str(e), -1

    def _parse_sources_list(output):
        """Parse page counts from 'gbrain sources list' output."""
        lines = output.strip().split("\n")
        total = 0
        never_synced = 0
        zero_pages = 0
        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                pages = int(parts[2])
                # Skip the auto-created 'default federated' source
                if len(parts) >= 2 and parts[0] == "default" and parts[1] == "federated":
                    continue
                total += 1
                if pages == 0:
                    zero_pages += 1
                if "never synced" in line.lower():
                    never_synced += 1
        return total, never_synced, zero_pages

    bun_path = HOME / ".bun" / "bin"
    gbrain_cmd = str(bun_path / "gbrain")

    if not bun_path.exists() or not Path(gbrain_cmd).exists():
        result = {"healthy": True, "issues": [], "gbrain_installed": False,
                "detail": "gbrain not installed"}
        _gbrain_cache = result
        _gbrain_cache_ts = time.time()
        return result
    if not (HOME / "brain").exists():
        _gbrain_cache = {"healthy": True, "issues": [], "gbrain_installed": False,
                "detail": "no brain directory"}
        _gbrain_cache_ts = time.time()
        return _gbrain_cache

    # Try 1: gbrain doctor --json
    out, _, rc = _run_gbrain([gbrain_cmd, "doctor", "--json"], timeout=45)
    if rc == 0 and out:
        try:
            data = json.loads(out)
            checks = data.get("doctor", {}).get("checks", [])
            failures = []
            for check in checks:
                name = check.get("name", "")
                status = check.get("status", "")
                msg = check.get("message", "")
                if status == "fail" and any(kw in name for kw in ["sync", "embed", "source", "cycle"]):
                    failures.append(f"{name}: {msg[:120]}")
                elif status == "warn" and name in ("sync_freshness", "cycle_freshness", "orphan_ratio"):
                    failures.append(f"{name}: {msg[:120]}")

            sync_checks = [c for c in checks if c.get("name") == "sync_freshness"]
            if sync_checks:
                sync_msg = sync_checks[0].get("message", "")
                if "never" in sync_msg.lower() or "0 page" in sync_msg.lower():
                    failures.append(f"Sources never synced or have 0 pages: {sync_msg[:150]}")

            if failures:
                for f in failures:
                    issues.append({"severity": "warning", "check": "gbrain_sources",
                                   "detail": f, "service": "gbrain"})
                result = {"healthy": False, "issues": issues,
                        "gbrain_installed": True, "detail": "; ".join(failures[:3])}
                _gbrain_cache = result
                _gbrain_cache_ts = time.time()
                return result

            overall = data.get("overall_health_score", -1)
            if 0 <= overall < 50:
                result = {"healthy": False, "issues": issues,
                        "gbrain_installed": True, "detail": f"Health score: {overall}/100"}
                _gbrain_cache = result
                _gbrain_cache_ts = time.time()
                return result

            result = {"healthy": True, "issues": issues,
                    "gbrain_installed": True, "detail": "All sources healthy"}
            _gbrain_cache = result
            _gbrain_cache_ts = time.time()
            return result
        except json.JSONDecodeError:
            pass  # Fall through

    # Try 2: gbrain sources list
    out, _, rc = _run_gbrain([gbrain_cmd, "sources", "list"], timeout=15)
    if rc == 0 and out:
        total, never_synced, zero_pages = _parse_sources_list(out)
        if never_synced > 0:
            issues.append({"severity": "warning", "check": "gbrain_sources",
                           "detail": f"{never_synced} source(s) never synced", "service": "gbrain"})
        if zero_pages > 0 and zero_pages == total:
            issues.append({"severity": "warning", "check": "gbrain_sources",
                           "detail": "all sources have 0 pages", "service": "gbrain"})
        elif zero_pages > 0:
            issues.append({"severity": "warning", "check": "gbrain_sources",
                           "detail": f"{zero_pages} source(s) have 0 pages", "service": "gbrain"})

        healthy = len(issues) == 0
        detail = f"{total} source(s), all synced" if healthy else "; ".join(
            i["detail"] for i in issues[:2])
        result = {"healthy": healthy, "issues": issues,
                "gbrain_installed": True, "detail": detail}
        _gbrain_cache = result
        _gbrain_cache_ts = time.time()
        return result

    result = {"healthy": True, "issues": issues,
            "gbrain_installed": True, "detail": "gbrain sources check unavailable"}
    _gbrain_cache = result
    _gbrain_cache_ts = time.time()
    return result


# ── Consolidated health ───────────────────────────────────────
def _build_health() -> dict:
    """Build the full consolidated health response."""
    checks = {}
    all_issues: list[dict] = []
    healthy = True

    for name, fn in [("resources", _check_resources), ("services", _check_services),
                      ("cron_health", _check_cron_health),
                      ("gbrain_sources", _check_gbrain_sources)]:
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
def _build_compact_health() -> dict:
    """Build minimal compact health response for public endpoint.

    Format: {"v": [...], "h": "j", "t": unix_timestamp}

    v array (8 values):
      [resources, services, no_errored_crons, no_stale_crons, nginx, ollama, gbrain, disk_ok]
      1 = healthy, -1 = unhealthy/warning
    h: single-char agent identifier (j = Joseph, m = Moses, t = Titus, g = Gisu)
    t: unix timestamp
    """
    r = _check_resources()
    s = _check_services()
    c = _check_cron_health()
    g = _check_gbrain_sources()

    resources_ok = r["healthy"]
    services_ok = s["healthy"]
    no_errored = len(c.get("errored", [])) == 0
    no_stale = len(c.get("stale", [])) == 0

    # Per-service status
    svc_map = {item["name"]: item["status"] for item in s.get("items", [])}
    nginx_ok = svc_map.get("nginx") == "running"
    ollama_ok = svc_map.get("ollama") == "running"
    gbrain_ok = svc_map.get("gbrain") == "running"

    # Disk threshold (80%+ = warning)
    disk_ok = r.get("data", {}).get("disk_percent", 0) < 80

    # gbrain sources check
    gbrain_sources_ok = g.get("healthy", True)

    v = [
        1 if resources_ok else -1,
        1 if services_ok else -1,
        1 if no_errored else -1,
        1 if no_stale else -1,
        1 if nginx_ok else -1,
        1 if ollama_ok else -1,
        1 if gbrain_ok else -1,
        1 if disk_ok else -1,
        1 if gbrain_sources_ok else -1,
    ]

    # Agent identifier — can be overridden via AGENT_ID env var
    h = AGENT_ID

    return {
        "v": v,
        "h": h,
        "t": int(time.time()),
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


@app.get("/api/v1/health/gbrain-sources")
async def health_gbrain_sources():
    result = _check_gbrain_sources()
    return {"server": SERVER_NAME, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/health")
async def health_public():
    """Public-facing health endpoint — compact format, no PII."""
    return _build_compact_health()


@app.get("/")
async def index():
    return _build_compact_health()


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=HEALTH_PORT, log_level="info")