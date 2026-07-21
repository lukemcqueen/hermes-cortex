#!/usr/bin/env python3
"""
agent-diagnostic.py — Collect agent diagnostics for remote troubleshooting.

Ran by agent-message-handler.py on DIAGNOSTIC_REQUEST, or standalone.

Outputs JSON with sections:
  handler    — state file contents, last run, processed count
  queue      — inbox depth, DLQ status from local bus
  system     — disk, memory, load
  agent      — version, git SHA
  cron       — handler cron last run time
  docker     — Docker container health (production stack)

Usage:
  python3 agent-diagnostic.py              # all checks
  python3 agent-diagnostic.py --check queue # specific check

When message-handler-state.json is present, its contents are included verbatim
so Moses can see what the handler was doing.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
HANDLER_STATE = STATE_DIR / "agent-message-state.json"
CONFIG_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"
CORTEX_REPO = HOME / "hermes-cortex"

# Bus API connection (used on worker agents that can't query DB directly)
BUS_URL = None


def _read_config(key: str) -> str:
    """Read a value from config files. Checks cortex-bus.conf then hermes-cortex/.env."""
    # Check cortex-bus.conf first
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip().strip("'\"")
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    # Fall back to .env
    env_file = CORTEX_REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip().strip("'\"")
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""


def _bus_get(endpoint: str) -> dict:
    """GET from remote bus API. Returns {} on failure."""
    try:
        import sys
        sys.path.insert(0, str(HOME / ".hermes-cortex" / "scripts"))
        from lib.cortex_bus import _get_auth_header, _read_config as _bus_cfg
        bus_url = _bus_cfg("CORTEX_BUS_URL") or os.environ.get("CORTEX_BUS_URL", "")
        if not bus_url:
            return {}
        scheme, creds = _get_auth_header()
        from urllib.request import Request, urlopen
        req = Request(f"{bus_url}{endpoint}")
        if creds:
            req.add_header("Authorization", f"{scheme} {creds}")
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run a command, return stdout or empty string."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def collect_handler() -> dict:
    """Handler state: last processed, counts, errors."""
    result = {}
    if HANDLER_STATE.exists():
        try:
            raw = HANDLER_STATE.read_text()
            state = json.loads(raw)
            result["state_file"] = state
            result["processed_count"] = len(state.get("processed_ids", []))
            # Calculate time since last result
            last_result = state.get("last_result")
            if last_result and "timestamp" in last_result:
                try:
                    ts = datetime.fromisoformat(last_result["timestamp"])
                    result["last_activity_seconds_ago"] = int(
                        (datetime.now(timezone.utc) - ts).total_seconds()
                    )
                except (ValueError, TypeError):
                    pass
        except (json.JSONDecodeError, OSError) as e:
            result["state_file_error"] = str(e)
    else:
        result["state_file"] = None
    return result


def collect_queue() -> dict:
    """Inbox depth and DLQ status from local bus."""
    agent = os.environ.get("AGENT_NAME", HOME.name)
    inbox = f"inbox_{agent}"
    dlq = f"inbox_{agent}_dlq"
    result = {}

    # Queue depth from bus API
    depth_data = _bus_get(f"/api/pgmq/depth/{inbox}")
    if depth_data:
        result["inbox_depth"] = depth_data.get("depth", -1)
    else:
        result["inbox_depth"] = -1

    # DLQ queue details
    dlq_data = _bus_get(f"/api/pgmq/queue/{dlq}")
    if dlq_data:
        result["dlq_depth"] = dlq_data.get("depth", 0) or dlq_data.get("message_count", 0)
        result["dlq_processing"] = dlq_data.get("processing", 0)
    else:
        result["dlq_depth"] = -1

    # Full queue list (on Moses, also check other agent DLQs)
    queues_data = _bus_get("/api/pgmq/queues")
    if isinstance(queues_data, dict) and "queues" in queues_data:
        all_dlq = [
            q for q in queues_data["queues"]
            if q.get("name", "").endswith("_dlq") and q.get("depth", 0) > 0
        ]
        result["all_dlq"] = [
            {"name": q["name"], "depth": q.get("depth", 0)}
            for q in all_dlq
        ]
    elif isinstance(queues_data, list):
        all_dlq = [
            q for q in queues_data
            if q.get("name", "").endswith("_dlq") and q.get("depth", 0) > 0
        ]
        result["all_dlq"] = [
            {"name": q["name"], "depth": q.get("depth", 0)}
            for q in all_dlq
        ]

    return result


def collect_system() -> dict:
    """Disk, memory, load."""
    result = {}

    # Disk
    disk = _run(["df", "-h", "/", "--output=pcent,used,size"])
    if disk:
        lines = disk.split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 3:
                result["disk"] = {
                    "used_pct": parts[0].strip().replace("%", ""),
                    "used": parts[1].strip(),
                    "total": parts[2].strip(),
                }

    # Memory
    mem = _run(["free", "-h"])
    if mem:
        for line in mem.split("\n"):
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 7:
                    result["memory"] = {
                        "total": parts[1],
                        "used": parts[2],
                        "available": parts[6],
                    }
                break

    # Load
    load = _run(["uptime"])
    if load:
        # Extract load averages (last 3 fields)
        parts = load.split()
        loads = [p.strip(",") for p in parts[-3:]]
        if len(loads) == 3:
            result["load"] = loads

    # Hostname
    hostname = _run(["hostname"])
    if hostname:
        result["hostname"] = hostname

    return result


def collect_agent() -> dict:
    """Agent version info."""
    result = {}

    # Git SHA from deployed code
    sha = _run(["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"])
    if sha:
        result["git_sha"] = sha
    else:
        # Try deployed scripts dir
        sha = _run(["git", "-C", str(HOME / ".hermes-cortex"), "rev-parse", "--short", "HEAD"])
        if sha:
            result["git_sha"] = sha
        else:
            result["git_sha"] = "unknown"

    result["agent_name"] = os.environ.get("AGENT_NAME", HOME.name)

    return result


def collect_cron() -> dict:
    """Handler cron last run time."""
    # Check the hermes scheduler's cron state files
    cron_state_dir = HOME / ".hermes" / "cron"
    handler_cron = None

    if cron_state_dir.exists():
        # Look for the agent-message-handler cron state
        for f in cron_state_dir.iterdir():
            if "handler" in f.name and f.suffix == ".json":
                try:
                    data = json.loads(f.read_text())
                    last_run = data.get("last_run_at")
                    if last_run:
                        handler_cron = {
                            "last_run": last_run,
                            "status": data.get("last_status", "?"),
                            "name": f.stem,
                        }
                except (json.JSONDecodeError, OSError):
                    pass
                break

    return {"handler_cron": handler_cron}


def collect_docker() -> dict:
    """Docker container health for production stack (MWI/MWEB)."""
    result = {}
    raw = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=10)
    if not raw:
        result["error"] = "Docker unavailable or no containers"
        return result

    containers = []
    unhealthy = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        name = parts[0].strip() if parts else line
        status = parts[1].strip() if len(parts) > 1 else ""
        entry = {"name": name, "status": status}
        containers.append(entry)
        if "unhealthy" in status.lower():
            unhealthy.append(name)

    result["total"] = len(containers)
    result["containers"] = containers
    result["healthy"] = len(unhealthy) == 0
    if unhealthy:
        result["unhealthy"] = unhealthy

    return result


def collect_docker() -> dict:
    """Docker container health for production stack (MWI/MWEB)."""
    result = {}
    raw = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=10)
    if not raw:
        result["error"] = "Docker unavailable or no containers"
        return result

    containers = []
    unhealthy = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        name = parts[0].strip() if parts else line
        status = parts[1].strip() if len(parts) > 1 else ""
        entry = {"name": name, "status": status}
        containers.append(entry)
        if "unhealthy" in status.lower():
            unhealthy.append(name)

    result["total"] = len(containers)
    result["containers"] = containers
    result["healthy"] = len(unhealthy) == 0
    if unhealthy:
        result["unhealthy"] = unhealthy

    return result


def collect_moses() -> dict:
    """Moses-only: query bus DB directly for DLQ details."""
    result = {}
    if HOME.name != "moses":
        return result

    # Only Moses has direct Docker access
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             "SELECT queue_name, count(*) FROM bus.messages "
             "WHERE queue_name LIKE '%_dlq' AND state = 'pending' "
             "AND enqueued_at > now() - interval '24 hours' "
             "GROUP BY queue_name ORDER BY queue_name"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            dlq_lines = []
            for line in r.stdout.strip().split("\n"):
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    dlq_lines.append({"queue": parts[0].strip(), "pending": int(parts[1].strip())})
            result["db_dlq"] = dlq_lines
    except Exception as e:
        result["db_error"] = str(e)

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent diagnostic collector")
    parser.add_argument("--check", choices=["handler", "queue", "system", "agent", "cron", "docker", "all"],
                        default="all", help="Which checks to run")
    args = parser.parse_args()

    checks = ["handler", "queue", "system", "agent", "cron", "docker"]
    if args.check == "all":
        run = checks
    else:
        run = [args.check]

    result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if "handler" in run:
        result["handler"] = collect_handler()
    if "queue" in run:
        result["queue"] = collect_queue()
    if "system" in run:
        result["system"] = collect_system()
    if "agent" in run:
        result["agent"] = collect_agent()
    if "cron" in run:
        result["cron"] = collect_cron()
    if "docker" in run:
        result["docker"] = collect_docker()

    # Moses-specific DB queries
    db = collect_moses()
    if db:
        result["moses"] = db

    # Flag any issues
    issues = []
    q = result.get("queue", {})
    if q.get("dlq_depth", 0) > 0:
        issues.append(f"DLQ has {q['dlq_depth']} pending messages")
    if q.get("inbox_depth", -1) > 10:
        issues.append(f"Inbox depth is {q['inbox_depth']}")
    s = result.get("system", {})
    if s.get("disk", {}).get("used_pct", "0") > "90":
        issues.append(f"Disk at {s['disk']['used_pct']}%")
    if issues:
        result["issues"] = issues

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
