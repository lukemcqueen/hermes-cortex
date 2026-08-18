#!/usr/bin/env python3
"""
health-vector.py — Hermes Cortex Agent Health Vector (9-item)

Two modes:
  1. Standalone:  python3 health-vector.py        → JSON to stdout
  2. HTTP server: python3 health-vector.py --serve  → serves on :8905

Service map (index → service name) from agent-registry.json:
  [0] resources           — system resources OK (CPU/mem not stressed)
  [1] services            — core services running
  [2] no_errored_crons    — no cron jobs with recent errors
  [3] no_stale_crons      — no cron jobs gone stale
  [4] nginx               — nginx process running
  [5] ollama              — Ollama process running
  [6] mycortex            — mycortex (gbrain replacement) doctor healthy
  [7] disk_ok             — disk has sufficient free space
  [8] mycortex_sources_ok — brain source directories exist

Output: {"v":[1,1,-1,1,1,1,1,1,1],"h":"hostname","t":1700000000}
  v[i] =  1  → healthy
  v[i] =  0  → not applicable (not installed on this agent)
  v[i] = -1  → unhealthy / down

The orchestrator (Moses) knows the service map and decodes this.
No authentication needed — deliberately minimal data.
"""
from __future__ import annotations

import json
import os
import re as _re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SERVICE_MAP = [
    "resources",
    "services",
    "no_errored_crons",
    "no_stale_crons",
    "nginx",
    "ollama",
    "mycortex",
    "disk_ok",
    "mycortex_sources_ok",
]

HOSTNAME = (
    os.environ.get("HEALTH_HOSTNAME")
    or os.uname().nodename.split(".")[0][:1].lower()
    or "m"
)


# ── Helpers ──

def _pgrep(pattern: str, exact: bool = True, full: bool = False) -> bool:
    """Check if a process matching pattern is running."""
    try:
        args = ["pgrep"]
        if exact:
            args += ["-x"]
        if full:
            args += ["-f"]
        args.append(pattern)
        r = subprocess.run(args, capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _systemd_active(unit: str) -> bool:
    """Check if a systemd unit is active (user or system scope)."""
    for scope in (["--user"], []):
        try:
            r = subprocess.run(
                ["systemctl", *scope, "is-active", unit],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip() == "active":
                return True
        except FileNotFoundError:
            print("expected — silently handled", file=sys.stderr)
    return False


def _launchd_active(label: str) -> bool:
    """Check if a launchd job is running (macOS)."""
    try:
        r = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return False
        return '"PID"' in r.stdout
    except FileNotFoundError:
        return False


def _docker_container(name: str) -> bool:
    """Check if a Docker container is running."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return name in r.stdout.splitlines()
    except FileNotFoundError:
        return False


def _url_ok(url: str, timeout: int = 3) -> bool:
    """Check if a URL responds with 200."""
    try:
        import urllib.request
        r = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


_is_linux = sys.platform.startswith("linux")
_is_macos = sys.platform == "darwin"


def _estimate_cron_interval(schedule: str | dict) -> int:
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
    m = _re.match(r'every\s+(\d+)\s*(m|min|h)', s, _re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return val * 60 if m.group(2) != 'h' else val * 3600

    parts = s.split()
    if len(parts) != 5:
        return 86400
    minute, hour, day, month, weekday = parts

    def _expand(field: str) -> list[int]:
        vals: list[int] = []
        for part in field.split(','):
            if '-' in part and part != '*':
                a, b = (int(x) for x in part.split('-', 1))
                vals.extend(range(a, b + 1))
            else:
                try:
                    vals.append(int(part))
                except ValueError:
                    print("expected — silently handled", file=sys.stderr)
        return sorted(set(vals))

    if day not in ('*', '?'):
        return 30 * 86400
    if weekday not in ('*', '?'):
        dow = _expand(weekday)
        if len(dow) > 1:
            gaps = [(dow[(i+1) % len(dow)] - dow[i]) % 7 for i in range(len(dow))]
            return max(gaps) * 86400
        return 7 * 86400
    if hour != '*':
        if ',' in hour:
            vals = sorted(int(x) for x in hour.split(','))
            gaps = [vals[i+1] - vals[i] for i in range(len(vals)-1)]
            gaps.append(24 - vals[-1] + vals[0])
            return max(gaps) * 3600
        elif '-' in hour:
            # Bounded hour range (e.g. 8-22): the max legit silence is the
            # overnight wrap gap (22:00 -> 08:00 = 10h), same semantics as the
            # comma-list branch above. Returning 1h falsely flagged these jobs
            # stale every night (observed 2026-08-19, orch-backlog-driver).
            try:
                a, b = (int(x) for x in hour.split('-', 1))
                return (24 - b + a) * 3600
            except ValueError:
                return 3600
        elif hour.startswith('*/'):
            return int(hour[2:]) * 3600
        return 86400
    if minute != '*':
        if ',' in minute:
            vals = sorted(int(x) for x in minute.split(','))
            gap = min(vals[i+1] - vals[i] for i in range(len(vals)-1)) if len(vals) > 1 else 1
            return max(gap * 60, 60)
        elif minute.startswith('*/'):
            return max(int(minute[2:]) * 60, 60)
        return 3600
    return 86400


# ── Health check functions ──

def check_resources() -> int:
    """System resources: CPU load average < 4x cores, memory not exhausted.

    Tries psutil first (cross-platform), falls back to sysctl on macOS
    or /proc/loadavg on Linux.
    """
    try:
        import psutil
        load1, load5, load15 = psutil.getloadavg()
        cpu_count = psutil.cpu_count() or 1
        if load1 > cpu_count * 4 or load5 > cpu_count * 4:
            return -1
        mem = psutil.virtual_memory()
        if mem.percent > 95:
            return -1
        return 1
    except ImportError:
        try:
            if _is_linux:
                with open("/proc/loadavg") as f:
                    parts = f.read().strip().split()
                    load1 = float(parts[0]) if parts else 0
            else:
                r = subprocess.run(
                    ["sysctl", "-n", "vm.loadavg"],
                    capture_output=True, text=True, timeout=5,
                )
                load1 = float(r.stdout.strip().split()[1]) if r.stdout.strip() else 0
            cpu_count = os.cpu_count() or 1
            if load1 > cpu_count * 4:
                return -1
            # Memory: df-based check on /
            r2 = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
            for line in r2.stdout.splitlines():
                if line.startswith("/"):
                    pct = int(line.split()[4].rstrip("%"))
                    if pct >= 95:
                        return -1
                    break
            return 1
        except Exception:
            return 1


def check_services() -> int:
    """Core services: check that installed services are running.

    On Linux, checks systemd units. Returns 1 if none are installed.
    On macOS, checks running processes. Returns 0 if none are installed.
    """
    if _is_linux:
        # gbrain-autopilot REMOVED from key services — decommissioned 2026-08-02
        # (mycortex replaces; a disabled unit is the intended state).
        key_services = ["nginx"]
        any_installed = False
        all_running = True
        for svc in key_services:
            if _systemd_active(svc + ".service") or _systemd_active(svc):
                any_installed = True
            else:
                all_running = False
        # ollama may run as a standalone process without a systemd unit
        if _pgrep("ollama"):
            any_installed = True
        else:
            all_running = False
        if not any_installed:
            return 0  # none installed — not applicable
        return 1 if all_running else -1
    else:
        # macOS: pgrep-based — return 1 if any found running, 0 if none installed
        for pat in ["nginx", "ollama"]:
            if _pgrep(pat, exact=True) or _pgrep(pat, exact=False, full=True):
                return 1
        return 0


def check_no_errored_crons() -> int:
    """No cron jobs with recent errors (from jobs.json)."""
    try:
        jobs_json = Path.home() / ".hermes" / "cron" / "jobs.json"
        if not jobs_json.exists():
            return -1
        data = json.loads(jobs_json.read_text())
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        for j in jobs:
            if not j.get("enabled", True):
                continue  # paused/disabled jobs don't run — frozen status is not actionable
            if j.get("last_status") == "error":
                return -1
        return 1
    except Exception:
        return -1


def check_no_stale_crons() -> int:
    """No cron jobs gone stale (schedule-aware, > 2x expected interval)."""
    try:
        jobs_json = Path.home() / ".hermes" / "cron" / "jobs.json"
        if not jobs_json.exists():
            return -1
        data = json.loads(jobs_json.read_text())
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        now = time.time()
        for j in jobs:
            if not j.get("enabled", True):
                continue  # paused/disabled jobs don't run — never stale
            last_run = j.get("last_run_at")
            if not last_run or "T" not in str(last_run):
                continue
            try:
                last = datetime.fromisoformat(str(last_run)).timestamp()
                elapsed = now - last
                sched = j.get("schedule", "")
                if sched:
                    expected = _estimate_cron_interval(sched)
                    if expected > 0 and elapsed > 2 * expected:
                        return -1
            except (ValueError, TypeError):
                continue
        return 1
    except Exception:
        return -1


def check_nginx() -> int:
    """nginx: 1 = running, 0 = not installed, -1 = installed but down."""
    if _pgrep("nginx"):
        return 1
    if not shutil.which("nginx"):
        return 0  # not installed on this system
    return -1


def check_ollama() -> int:
    """Ollama: 1 = running, 0 = not installed, -1 = installed but down."""
    if not shutil.which("ollama"):
        return 0  # not installed on this system
    if _is_linux:
        if _systemd_active("ollama.service") or _systemd_active("ollama"):
            return 1
    if _is_macos:
        if _launchd_active("com.ollama.serve"):
            return 1
    if _pgrep("ollama"):
        return 1
    return -1


# mycortex doctor result cache. The check shells out to `mycortex doctor --json`
# (~2s+ per run); health pollers hit the endpoint every few minutes, so a short
# TTL keeps each /health request fast without masking real state for long.
# (Same pattern as the retired health-server.py gbrain cache.)
_MYCORTEX_CACHE = {"t": 0.0, "result": 0}
_MYCORTEX_TTL = 60


def check_mycortex() -> int:
    """mycortex (gbrain replacement): 1 = healthy, 0 = not installed, -1 = installed but down."""
    cli = os.path.expanduser("~/.hermes-cortex/scripts/mycortex")
    if not os.path.exists(cli):
        return 0  # not installed on this system
    now = time.time()
    if now - _MYCORTEX_CACHE["t"] < _MYCORTEX_TTL:
        return _MYCORTEX_CACHE["result"]
    try:
        r = subprocess.run(
            [cli, "doctor", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        # doctor exits 0 iff ok — authoritative. stdout mixes human lines
        # with a trailing JSON line, so fall back to rc on parse failure.
        if r.returncode != 0:
            result = -1
        else:
            try:
                data = json.loads(r.stdout)
                result = 1 if data.get("ok") else -1
            except (json.JSONDecodeError, ValueError):
                result = 1  # rc=0 means doctor passed
    except Exception:
        result = -1
    _MYCORTEX_CACHE["t"] = now
    _MYCORTEX_CACHE["result"] = result
    return result


def check_disk_ok() -> int:
    """Disk: root partition has > 10% free space."""
    try:
        r = subprocess.run(
            ["df", "-h", "/"] if _is_macos else ["df", "/", "--output=pcent"],
            capture_output=True, text=True, timeout=5,
        )
        lines = r.stdout.strip().splitlines()
        if len(lines) >= 2:
            if _is_macos:
                parts = lines[1].split()
                if len(parts) >= 5:
                    pct = int(parts[4].replace("%", ""))
                    return 1 if pct < 90 else -1
            else:
                pct = int(lines[1].replace("%", "").strip())
                return 1 if pct < 90 else -1
        return 1
    except Exception:
        return 1


def check_mycortex_sources_ok() -> int:
    """mycortex source directories exist and are non-empty."""
    brain_home = os.path.expanduser("~/brain")
    bp = Path(brain_home)
    if not bp.is_dir():
        return -1
    for entry in bp.iterdir():
        if entry.is_dir() and any(entry.iterdir()):
            return 1
    return -1


CHECK_FUNCTIONS = [
    check_resources,
    check_services,
    check_no_errored_crons,
    check_no_stale_crons,
    check_nginx,
    check_ollama,
    check_mycortex,
    check_disk_ok,
    check_mycortex_sources_ok,
]


def get_vector() -> list[int]:
    """Run all checks and return the status vector."""
    return [fn() for fn in CHECK_FUNCTIONS]


def build_report() -> dict:
    """Build the full health report dict."""
    return {
        "v": get_vector(),
        "h": HOSTNAME,
        "t": int(time.time()),
    }


def serve_http(port: int = 8905):
    """Run as a lightweight HTTP server."""
    # ThreadingHTTPServer: pollers (hourly report, fleet watchdogs, dashboard)
    # hit the endpoint within seconds of each other at :00. A plain HTTPServer
    # serializes them — one slow request (cold mycortex cache) queues the rest
    # past their client timeouts → false "unreachable". Threaded so a slow
    # request never blocks another.
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health" or self.path == "/":
                report = build_report()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(report).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # quiet

    server = ThreadingHTTPServer(("127.0.0.1", port), HealthHandler)
    print(f"🧬 Health vector server on :{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


# ── Main ──

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 13006
        serve_http(port)
    elif len(sys.argv) > 1 and sys.argv[1] == "--check":
        vec = get_vector()
        icons = {1: "✅", 0: "➖", -1: "❌"}
        print(f"Health Vector for {HOSTNAME}")
        print(f"Raw: ({' '.join(str(v) for v in vec)})")
        print()
        for label, v in zip(SERVICE_MAP, vec):
            print(f"  {icons[v]} {label}")
    else:
        print(json.dumps(build_report()))


if __name__ == "__main__":
    main()