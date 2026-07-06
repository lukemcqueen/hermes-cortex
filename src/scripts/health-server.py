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
import logging
import os
import platform
import re
import signal
import socket
import ssl
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── Shared port arbitration ────────────────────────────────────
from _port_arbitration import check_and_claim_port, release_port, setup_dirs as _ensure_dirs_server

# ── Logging setup ──────────────────────────────────────────────
_log = logging.getLogger("health-server")
_log.setLevel(logging.DEBUG)
_handler = logging.StreamHandler(stream=sys.stdout)
_handler.setLevel(logging.DEBUG)
_fmt = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_handler.setFormatter(_fmt)
_log.addHandler(_handler)
_log.propagate = False  # don't double-log through uvicorn's root logger

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

# External health URL for self-verification
# Set EXTERNAL_HEALTH_URL to the URL other agents use to reach this health server.
# If unset, the health check is skipped and reported as "not configured".
EXTERNAL_HEALTH_URL = os.environ.get("EXTERNAL_HEALTH_URL", "")

# SSL cert paths — used for cert expiration checking
SSL_CERT_PATH = os.environ.get("CORTEX_SSL_CERT_PATH", "")
SSL_CERT_KEY_PATH = os.environ.get("CORTEX_SSL_CERT_KEY_PATH", "")

# Startup timestamp for uptime tracking
_STARTUP_TS = time.time()

# Compact health response cache — recompute every N seconds
_COMPACT_CACHE: dict | None = None
_COMPACT_CACHE_TS: float = 0.0
_COMPACT_CACHE_TTL: float = 30.0  # seconds

app = FastAPI(title=f"Health Server — {AGENT_ID}", version="1.0.0")


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


# ── Timing & deadline helpers ─────────────────────────────────
_tpool = ThreadPoolExecutor(max_workers=2)


def _run_with_deadline(fn, timeout: float, label: str = "check"):
    """Run `fn()` in a thread with a hard deadline.

    Returns (result, elapsed, timed_out) tuple.
    If the deadline is exceeded, returns (None, timeout, True).
    """
    fut = _tpool.submit(fn)
    start = time.monotonic()
    try:
        result = fut.result(timeout=timeout)
        elapsed = time.monotonic() - start
        return result, round(elapsed, 3), False
    except TimeoutError:
        elapsed = time.monotonic() - start
        _log.warning("DEADLINE EXCEEDED — %s did not finish in %.1fs (%.1fs elapsed)", label, timeout, elapsed)
        return None, round(elapsed, 3), True
    except Exception as e:
        elapsed = time.monotonic() - start
        _log.error("DEADLINE ERROR — %s failed after %.1fs: %s", label, elapsed, e)
        return None, round(elapsed, 3), True


def _timed(label: str, fn, *args, **kwargs):
    """Run `fn(*args, **kwargs)` and return (result, elapsed_seconds).

    Always returns — no exception escapes. On error, logs + returns
    (None, elapsed).
    """
    start = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.monotonic() - start
        if elapsed > 2.0:
            _log.info("SLOW CHECK — %s took %.1fs", label, elapsed)
        return result, round(elapsed, 3)
    except Exception:
        elapsed = time.monotonic() - start
        _log.error("CHECK FAILED — %s crashed after %.1fs\n%s", label, elapsed, traceback.format_exc())
        return None, round(elapsed, 3)


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
def _estimate_interval(schedule: str | dict) -> int:
    """Estimate expected interval in seconds from a cron schedule.

    Accepts a string ('0 6 * * 1') or dict ({kind, expr, display}).
    Uses the most significant constrained field to determine cadence.
    Stale check uses: elapsed > 2x expected.
    """
    if not schedule:
        return 86400
    if isinstance(schedule, dict):
        s = (schedule.get("expr") or schedule.get("display") or "").strip()
    else:
        s = str(schedule).strip()

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
            # Max gap between scheduled hours (including overnight wrap)
            gaps = [vals[i+1] - vals[i] for i in range(len(vals)-1)]
            gaps.append(24 - vals[-1] + vals[0])
            return max(gaps) * 3600
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
_GBRAIN_CACHE_TTL = 900  # 15 minutes

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


# ── External reachability ──────────────────────────────────────
_CERT_EXPIRY_CACHE: tuple | None = None
_CERT_EXPIRY_CACHE_TS: float = 0.0
_CERT_EXPIRY_CACHE_TTL: float = 3600  # 1 hour

def _check_external_reachability() -> dict:
    """Test the external health URL and SSL cert expiry.

    Returns:
        {"reachable": bool, "status_code": int|None, "url_tested": str,
         "cert_expiry_days": int|None, "cert_expiry_warning": str|None, ...}
    """
    result = {
        "reachable": False,
        "status_code": None,
        "url_tested": EXTERNAL_HEALTH_URL or "(not configured)",
        "cert_expiry_days": None,
        "cert_expiry_warning": None,
        "detail": "",
        "healthy": True,  # not-configured/unreachable is informational, not unhealthy
    }

    # ── Check SSL cert expiry ──
    cert_expiry_days = None
    cert_warning = None
    global _CERT_EXPIRY_CACHE, _CERT_EXPIRY_CACHE_TS
    now = time.time()
    if _CERT_EXPIRY_CACHE is not None and (now - _CERT_EXPIRY_CACHE_TS) < _CERT_EXPIRY_CACHE_TTL:
        cert_expiry_days, cert_warning = _CERT_EXPIRY_CACHE
    elif SSL_CERT_PATH:
        try:
            ctx = ssl.create_default_context()
            with open(SSL_CERT_PATH, "rb") as f:
                cert = ctx._wrap_pem_cert(f.read())  # internal-ish but works
        except Exception:
            try:
                from cryptography import x509
                from cryptography.hazmat.backends import default_backend
                with open(SSL_CERT_PATH, "rb") as f:
                    cert_data = f.read()
                cert_obj = x509.load_pem_x509_certificate(cert_data, default_backend())
                not_after = cert_obj.not_valid_after_utc if hasattr(cert_obj, "not_valid_after_utc") else cert_obj.not_valid_after
                remaining = (not_after - datetime.now(timezone.utc)).days
                cert_expiry_days = remaining
                if remaining < 0:
                    cert_warning = f"CRITICAL — SSL cert expired {abs(remaining)} day(s) ago"
                elif remaining < 7:
                    cert_warning = f"WARNING — SSL cert expires in {remaining} day(s)"
                elif remaining < 30:
                    cert_warning = f"INFO — SSL cert expires in {remaining} day(s)"
            except Exception:
                # Fallback: cryptography not installed or cert unreadable (root-owned)
                _log.warning("cryptography not available or cert unreadable — skipping cert expiry check")
                pass
        _CERT_EXPIRY_CACHE = (cert_expiry_days, cert_warning)
        _CERT_EXPIRY_CACHE_TS = time.time()

    result["cert_expiry_days"] = cert_expiry_days
    result["cert_expiry_warning"] = cert_warning

    # ── Check external URL reachability ──
    if not EXTERNAL_HEALTH_URL:
        result["detail"] = "EXTERNAL_HEALTH_URL not configured"
        return result

    try:
        from urllib.parse import urlparse
        parsed = urlparse(EXTERNAL_HEALTH_URL)
        host = parsed.hostname or "unknown"
        port = parsed.port or 443

        # Test TCP connectivity to the external port
        # This validates DNS resolution + firewall + nginx is listening
        addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        result["reachable"] = True
        result["status_code"] = 0
        result["detail"] = f"TCP connected to {host}:{port}"
    except socket.gaierror as e:
        result["detail"] = f"DNS resolution failed: {e}"
    except (socket.timeout, OSError) as e:
        result["detail"] = f"TCP connection failed: {e}"

    return result


# ── Consolidated health ───────────────────────────────────────
def _build_health() -> dict:
    """Build the full consolidated health response with per-check timing."""
    checks = {}
    all_issues: list[dict] = []
    healthy = True
    timing: dict[str, float] = {}

    checks_list = [
        ("resources", _check_resources),
        ("services", _check_services),
        ("cron_health", _check_cron_health),
        ("gbrain_sources", _check_gbrain_sources),
        ("external_reachability", _check_external_reachability),
    ]

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_timed, name, fn): name for name, fn in checks_list}
        for future in as_completed(futures):
            name = futures[future]
            result, elapsed = future.result()
            timing[name] = elapsed
            if result is None:
                result = {"healthy": False, "issues": [{"severity": "critical", "check": name,
                           "detail": f"Check crashed or timed out after {elapsed}s"}]}
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

    total_elapsed = sum(timing.values())
    _log.info("HEALTH — %s total=%.1fs %s", AGENT_ID, total_elapsed,
              " ".join(f"{k}={v}s" for k, v in sorted(timing.items())))

    return {
        "server": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": _get_uptime(),
        "healthy": healthy,
        "checks": checks,
        "issues": all_issues,
        "timing": timing,
        "external_reachability": checks.get("external_reachability", {}),
    }


# ── Routes ────────────────────────────────────────────────────
def _build_compact_health() -> dict:
    """Build minimal compact health response for public endpoint.

    Format: {"v": [...], "h": "j", "t": unix_timestamp}

    v array (9 values):
      [resources, services, no_errored_crons, no_stale_crons, nginx, ollama,
       gbrain, disk_ok, gbrain_sources_ok]
      1 = healthy, -1 = unhealthy/warning
    h: single-char agent identifier (j = Joseph, m = Moses, t = Titus, g = Gisu)
    t: unix timestamp
    """
    _start = time.monotonic()

    global _COMPACT_CACHE, _COMPACT_CACHE_TS
    now_ts = time.time()
    if _COMPACT_CACHE is not None and (now_ts - _COMPACT_CACHE_TS) < _COMPACT_CACHE_TTL:
        # Update timestamp only — serve cached vector
        _COMPACT_CACHE["t"] = int(now_ts)
        return _COMPACT_CACHE

    # Run checks in parallel
    r = s = c = g = None
    r_elapsed = s_elapsed = c_elapsed = 0.0
    g_elapsed = 0.0

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_r = pool.submit(_timed, "resources", _check_resources)
        f_s = pool.submit(_timed, "services", _check_services)
        f_c = pool.submit(_timed, "cron_health", _check_cron_health)
        # gbrain sources gets a hard 5s deadline (was 20s)
        f_g = pool.submit(_run_with_deadline, _check_gbrain_sources, 5.0, "gbrain_sources")

        for f in as_completed([f_r, f_s, f_c, f_g]):
            if f is f_r:
                r, r_elapsed = f.result()
            elif f is f_s:
                s, s_elapsed = f.result()
            elif f is f_c:
                c, c_elapsed = f.result()
            elif f is f_g:
                g, g_elapsed, g_timedout = f.result()
                if g_timedout or g is None:
                    g = {"healthy": False, "issues": [{"severity": "warning", "check": "gbrain_sources",
                          "detail": f"Deadline exceeded ({g_elapsed}s) — degraded response"}]}

    total_elapsed = round(time.monotonic() - _start, 3)
    _log.info("COMPACT — %s total=%.1fs resources=%.1fs services=%.1fs crons=%.1fs gbrain=%.1fs",
              AGENT_ID, total_elapsed, r_elapsed, s_elapsed, c_elapsed, g_elapsed)

    if total_elapsed > 5.0:
        _log.warning("SLOW COMPACT HEALTH — %s took %.1fs", AGENT_ID, total_elapsed)

    # Guard against crashed checks — degrade gracefully
    if r is None:
        r = {"healthy": False, "issues": [], "data": {}}
    if s is None:
        s = {"healthy": False, "issues": [], "items": []}
    if c is None:
        c = {"errored": ["check-failed"], "stale": [], "healthy": False}

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

    result = {
        "v": v,
        "h": h,
        "t": int(time.time()),
    }
    # Store in cache
    _COMPACT_CACHE = result
    _COMPACT_CACHE_TS = time.time()

    return result


# ── Routes ────────────────────────────────────────────────────
@app.get("/api/v1/health")
async def health_v1():
    return _build_health()


@app.get("/api/v1/health/resources")
async def health_resources():
    result = _check_resources()
    return {"server": AGENT_ID, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/api/v1/health/services")
async def health_services():
    result = _check_services()
    return {"server": AGENT_ID, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/api/v1/health/gbrain-sources")
async def health_gbrain_sources():
    result = _check_gbrain_sources()
    return {"server": AGENT_ID, "timestamp": datetime.now(timezone.utc).isoformat(), **result}


@app.get("/health")
async def health_public():
    """Public-facing health endpoint — compact format, no PII."""
    return _build_compact_health()


@app.get("/")
async def index():
    return _build_compact_health()


# ── Startup helpers ────────────────────────────────────────────
def _ensure_dirs():
    """Create required directories if missing.
    
    Prevents crash-looping from 'Failed to set up standard output: No such file or directory'.
    Delegates to shared _port_arbitration module for consistency.
    """
    _ensure_dirs_server(str(HOME / ".hermes" / "health-server"))


_PID_FILE: Path | None = None
_PID_PATH = HOME / ".hermes" / "health-server" / "server.pid"


def _check_port_conflict() -> bool:
    """Check if HEALTH_PORT is already in use by another health-server.
    
    Delegates to shared _port_arbitration.check_and_claim_port().
    """
    global _PID_FILE, _PID_PATH
    _PID_FILE = _PID_PATH
    return check_and_claim_port("127.0.0.1", HEALTH_PORT, "health-server", pid_path=_PID_PATH)


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # Layer 1: Ensure directories exist before any I/O
    _ensure_dirs()
    _log.info("STARTING — server=%s agent=%s port=%d os=%s python=%s",
              SERVER_NAME, AGENT_ID, HEALTH_PORT, _get_os(), platform.python_version())
    _log.info("CONFIG — _STARTUP_TS=%d HOME=%s", int(_STARTUP_TS), HOME)

    # Layer 2: Port arbitration — crash-loop prevention
    if not _check_port_conflict():
        # Port is held by another health-server — exit 0 (not a failure)
        _log.info("HANDOFF — existing health-server owns port %d, this instance exiting 0", HEALTH_PORT)
        sys.exit(0)

    # Log on graceful shutdown
    def _shutdown_log(signum, frame):
        _log.warning("SHUTDOWN — received signal %d, exiting", signum)
        if _PID_FILE and _PID_FILE.exists():
            _PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown_log)
    signal.signal(signal.SIGINT, _shutdown_log)

    # Layer 3: Run — if uvicorn fails, systemd will try again (rare with port arbitration)
    try:
        uvicorn.run(app, host="127.0.0.1", port=HEALTH_PORT, log_level="info")
    finally:
        if _PID_FILE and _PID_FILE.exists():
            _PID_FILE.unlink(missing_ok=True)