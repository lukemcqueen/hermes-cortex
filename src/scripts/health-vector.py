#!/usr/bin/env python3
"""
health-vector.py — Hermes Cortex Agent Health Vector

Two modes:
  1. Standalone:  python3 health-vector.py        → JSON to stdout
  2. HTTP server: python3 health-vector.py --serve  → serves on :13006

Service map (index → service name):
  [0] nginx
  [1] Ollama
  [2] gbrain
  [3] Cortex Dashboard
  [4] Langfuse (web)
  [5] Langfuse (worker)
  [6] Docker daemon
  [7] Hermes Gateway

Output: {"v":[1,-1,0,1,0,1,-1,1],"h":"hostname","t":1700000000}
  v[i] =  1  → service is running
  v[i] =  0  → service not applicable (not installed on this agent)
  v[i] = -1  → service is down

The orchestrator (Moses) knows the service map and decodes this.
No authentication needed — this is deliberately minimal data.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SERVICE_MAP = [
    "resources",
    "services",
    "no_errored_crons",
    "no_stale_crons",
    "nginx",
    "ollama",
    "gbrain",
    "disk_ok",
    "gbrain_sources_ok",
]

HOSTNAME = os.environ.get("HEALTH_HOSTNAME", os.uname().nodename.split(".")[0])


# ── Per-service health checks ──

def _pgrep(pattern: str, exact: bool = True, full: bool = False) -> bool:
    """Check if a process matching pattern is running.
    
    Args:
        pattern: Process name or command substring to match.
        exact: Match exact process name (pgrep -x).
        full: Match against full command line (pgrep -f).
    """
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
            pass
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


def check_nginx() -> int:
    """nginx: process check (master process)."""
    if _pgrep("nginx"):
        return 1
    return -1


def check_ollama() -> int:
    """Ollama: systemd/launchd or process."""
    if _is_linux:
        if _systemd_active("ollama.service") or _systemd_active("ollama"):
            return 1
    if _is_macos:
        if _launchd_active("com.ollama.serve"):
            return 1
    if _pgrep("ollama"):
        return 1
    return -1


def check_gbrain() -> int:
    """gbrain: systemd/launchd or process."""
    if _is_linux:
        if _systemd_active("gbrain-autopilot.service") or \
           _systemd_active("com.gbrain.autopilot"):
            return 1
    if _is_macos:
        if _launchd_active("com.gbrain.autopilot"):
            return 1
    if _pgrep("gbrain", exact=False, full=True):
        return 1
    return -1


def check_cortex_dashboard() -> int:
    """Cortex Dashboard: local port check or process."""
    if _url_ok("http://127.0.0.1:8901/api/health"):
        return 1
    if _pgrep("cortex-dashboard") or _pgrep("dashboard"):
        return 1
    return -1


def check_langfuse_web() -> int:
    """Langfuse web: Docker container."""
    if _docker_container("langfuse-langfuse-web-1"):
        return 1
    return -1


def check_langfuse_worker() -> int:
    """Langfuse worker: Docker container."""
    if _docker_container("langfuse-langfuse-worker-1"):
        return 1
    return -1


def check_docker() -> int:
    """Docker daemon: socket or process."""
    if _pgrep("dockerd") or Path("/var/run/docker.sock").exists():
        return 1
    return -1


def check_hermes_gateway() -> int:
    """Hermes Gateway: process or port."""
    if _pgrep("gateway run", exact=False, full=True):
        return 1
    if _url_ok("http://127.0.0.1:8900/"):
        return 1
    return -1


CHECK_FUNCTIONS = [
    check_nginx,
    check_ollama,
    check_gbrain,
    check_cortex_dashboard,
    check_langfuse_web,
    check_langfuse_worker,
    check_docker,
    check_hermes_gateway,
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


def serve_http(port: int = 13006):
    """Run as a lightweight HTTP server."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

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

    server = HTTPServer(("127.0.0.1", port), HealthHandler)
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
        # Human-readable check output
        vec = get_vector()
        labels = ["nginx", "ollama", "gbrain", "dashboard", "langfuse-web",
                   "langfuse-worker", "docker", "gateway"]
        icons = {1: "✅", 0: "➖", -1: "❌"}
        print(f"Health Vector for {HOSTNAME}")
        print(f"Raw: ({' '.join(str(v) for v in vec)})")
        print()
        for label, v in zip(labels, vec):
            print(f"  {icons[v]} {label}")
    else:
        print(json.dumps(build_report()))


if __name__ == "__main__":
    main()