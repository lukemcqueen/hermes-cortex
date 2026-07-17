#!/usr/bin/env python3
"""heartbeat.py — System health watchdog for Hermes/gbrain stack.

Checks critical daemons and services:
  - Ollama (LLM server)
  - gbrain sync daemon
  - Hermes gateway
  - Langfuse Docker services (ClickHouse, MinIO, Redis)
  - Memory-to-brain sync freshness
  - Agent inbox scan freshness
  - Disk space
  - Cron job health

Outputs a concise health report. Designed for cron integration:
  - Non-empty stdout on FAILURE → cron delivers alert
  - Empty stdout when healthy → silent (watchdog pattern)
  - Use --report to force output regardless of health
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
NOW = datetime.now().astimezone()

# Platform detection — cached after first call
_IS_LINUX: Optional[bool] = None


def _is_linux() -> bool:
    global _IS_LINUX
    if _IS_LINUX is None:
        try:
            subprocess.run(["launchctl", "list"], capture_output=True, timeout=5)
            _IS_LINUX = False
        except FileNotFoundError:
            _IS_LINUX = True
    return _IS_LINUX


def check_systemd(unit_name: str) -> dict:
    """Check systemd service status.

    Tries user scope first, falls back to system scope.
    Returns UP/ DOWN/ ERROR with detail.
    """
    for scope, label in [(["--user"], "user"), ([], "system")]:
        try:
            result = subprocess.run(
                ["systemctl", *scope, "is-active", unit_name],
                capture_output=True, text=True, timeout=10,
            )
            status = result.stdout.strip()
            # systemctl returns active/inactive/failed — exit 0 only for active
            if result.returncode == 0 and status == "active":
                return {"status": "UP", "detail": f"{unit_name} ({label})"}
            if result.returncode != 0 and status in ("inactive", "dead", "failed"):
                continue  # try other scope
            if result.returncode == 0:
                return {"status": "UP", "detail": f"{unit_name} ({label})"}
        except FileNotFoundError:
            return {"status": "ERROR", "detail": "systemctl not found"}
        except Exception as e:
            return {"status": "ERROR", "detail": str(e)}

    # Neither scope found it active
    try:
        # Last attempt — just check if any process called unit_name is running
        proc_name = unit_name.split(".")[-1] if "." in unit_name else unit_name
        pg = subprocess.run(
            ["pgrep", "-x", proc_name], capture_output=True, timeout=5,
        )
        if pg.returncode == 0:
            return {"status": "DEGRADED", "detail": f"{unit_name} (process found, no systemd unit)"}
    except Exception:
        pass

    return {"status": "DOWN", "detail": f"{unit_name} not active in any scope"}


def check_service(label: str) -> dict:
    """Check service using systemd (Linux) or launchd (macOS)."""
    if _is_linux():
        return check_systemd(label)
    # macOS launchd path (unchanged, kept for cross-platform compat)
    return _check_launchd(label)


def _check_launchd(job_label: str) -> dict:
    """Check if a launchd job is running and healthy (macOS)."""
    try:
        result = subprocess.run(
            ["launchctl", "list", job_label],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"status": "DOWN", "detail": f"launchctl list failed: {result.stderr.strip()}"}

        stdout = result.stdout.strip()
        pid_match = re.search(r'"PID"\s*=\s*(\d+);', stdout)
        exit_match = re.search(r'"LastExitStatus"\s*=\s*(\d+);', stdout)

        if pid_match:
            pid = pid_match.group(1)
            exit_code = int(exit_match.group(1)) if exit_match else 0
            if exit_code != 0:
                return {"status": "DEGRADED", "detail": f"Running (PID {pid}) but last exit was {exit_code}"}
            return {"status": "UP", "detail": f"PID {pid}"}

        # Fallback: tab-separated format (older macOS)
        parts = stdout.split("\t")
        if len(parts) >= 2:
            pid = parts[0]
            exit_code = parts[1]
            if pid == "-":
                return {"status": "DOWN", "detail": f"No PID (exit code: {exit_code})"}
            if exit_code not in ("0", "-"):
                return {"status": "DEGRADED", "detail": f"Running (PID {pid}) but last exit was {exit_code}"}
            return {"status": "UP", "detail": f"PID {pid}"}

        return {"status": "ERROR", "detail": f"Unrecognized launchctl output: {stdout[:200]}"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_disk_usage(path: str = "/") -> dict:
    """Check disk usage."""
    try:
        result = subprocess.run(
            ["df", "-h", path], capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            fields = lines[1].split()
            used_pct = fields[4] if len(fields) >= 5 else "?"
            pct_str = used_pct.rstrip("%")
            try:
                pct = int(pct_str)
                status = "UP" if pct < 85 else "DEGRADED" if pct < 95 else "DOWN"
                return {"status": status, "detail": f"{used_pct} used on {path}"}
            except ValueError:
                return {"status": "UP", "detail": f"{used_pct} used on {path} (unparseable)"}
        return {"status": "ERROR", "detail": "Could not parse df output"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_docker_containers() -> dict:
    """Check essential Docker containers (ClickHouse, MinIO, Redis) for Langfuse."""
    containers = {
        "ClickHouse": "langfuse-clickhouse-1",
        "MinIO": "langfuse-minio-1",
        "Redis": "langfuse-redis-1",
    }
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"status": "UNKNOWN", "detail": "Docker not available"}

        running = {}
        for line in result.stdout.strip().split("\n"):
            if "\t" in line:
                name, status = line.split("\t", 1)
                running[name] = status

        issues = []
        for label, container_name in containers.items():
            if container_name not in running:
                issues.append(f"{label} not running")
            elif "Up" not in running[container_name]:
                issues.append(f"{label}: {running[container_name]}")

        if issues:
            return {"status": "DEGRADED", "detail": "; ".join(issues)}
        return {"status": "UP", "detail": "all containers healthy"}
    except FileNotFoundError:
        return {"status": "UNKNOWN", "detail": "Docker not installed"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_memory_sync_freshness() -> dict:
    """Check when memory was last synced to brain."""
    current = BRAIN_SHARED / "hermes-memory" / "current.md"
    if not current.exists():
        return {"status": "UNKNOWN", "detail": "No current.md — sync may not have run yet"}
    mtime = datetime.fromtimestamp(current.stat().st_mtime, tz=timezone.utc).astimezone()
    age = NOW - mtime
    if age < timedelta(hours=8):
        return {"status": "UP", "detail": f"Last sync: {age.total_seconds() / 60:.0f}m ago"}
    elif age < timedelta(hours=24):
        return {"status": "DEGRADED", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago"}
    else:
        return {"status": "DOWN", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago — stale!"}


def check_gateway_log() -> dict:
    """Quick check if gateway has logged recently."""
    log_dir = HERMES_HOME / "logs"
    if not log_dir.exists():
        return {"status": "UNKNOWN", "detail": "No log directory"}
    # Find most recently modified log file and report its age
    try:
        latest = max(
            (f for f in log_dir.iterdir() if f.is_file() and f.suffix in (".log", ".json")),
            key=lambda f: f.stat().st_mtime,
            default=None
        )
        if latest is None:
            return {"status": "UNKNOWN", "detail": "No log files found"}
        age = NOW - datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).astimezone()
        if age < timedelta(hours=1):
            return {"status": "UP", "detail": f"Last log entry: {age.total_seconds() / 60:.0f}m ago"}
        elif age < timedelta(hours=6):
            return {"status": "DEGRADED", "detail": f"Last log entry: {age.total_seconds() / 60:.0f}m ago"}
        else:
            return {"status": "DOWN", "detail": f"Last log entry: {age.total_seconds() / 60:.0f}m ago — gateway may be stalled!"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}
def check_disk_usage(path: str = "/") -> dict:
    """Check disk usage."""
    try:
        result = subprocess.run(
            ["df", "-h", path], capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            fields = lines[1].split()
            used_pct = fields[4] if len(fields) >= 5 else "?"
            pct_str = used_pct.rstrip("%")
            try:
                pct = int(pct_str)
                status = "UP" if pct < 85 else "DEGRADED" if pct < 95 else "DOWN"
                return {"status": status, "detail": f"{used_pct} used on {path}"}
            except ValueError:
                return {"status": "UP", "detail": f"{used_pct} used on {path} (unparseable)"}
        return {"status": "ERROR", "detail": "Could not parse df output"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_docker_containers() -> dict:
    """Check essential Docker containers (ClickHouse, MinIO, Redis) for Langfuse."""
    containers = {
        "ClickHouse": "langfuse-clickhouse-1",
        "MinIO": "langfuse-minio-1",
        "Redis": "langfuse-redis-1",
    }
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"status": "UNKNOWN", "detail": "Docker not available"}

        running = {}
        for line in result.stdout.strip().split("\n"):
            if "\t" in line:
                name, status = line.split("\t", 1)
                running[name] = status

        issues = []
        for label, container_name in containers.items():
            if container_name not in running:
                issues.append(f"{label} not running")
            elif "Up" not in running[container_name]:
                issues.append(f"{label}: {running[container_name]}")

        if issues:
            return {"status": "DEGRADED", "detail": "; ".join(issues)}
        return {"status": "UP", "detail": "all containers healthy"}
    except FileNotFoundError:
        return {"status": "UNKNOWN", "detail": "Docker not installed"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_memory_sync_freshness() -> dict:
    """Check when memory was last synced to brain."""
    current = BRAIN_SHARED / "hermes-memory" / "current.md"
    if not current.exists():
        return {"status": "UNKNOWN", "detail": "No current.md — sync may not have run yet"}
    mtime = datetime.fromtimestamp(current.stat().st_mtime, tz=timezone.utc).astimezone()
    age = NOW - mtime
    if age < timedelta(hours=8):
        return {"status": "UP", "detail": f"Last sync: {age.total_seconds() / 60:.0f}m ago"}
    elif age < timedelta(hours=24):
        return {"status": "DEGRADED", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago"}
    else:
        return {"status": "DOWN", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago — stale!"}


def check_gbrain_sources() -> dict:
    """Check gbrain source health: flag 'never synced' or '0 pages' sources.

    Gracefully degrades when gbrain doctor is unavailable:
      - Falls back to parsing 'sources list' output
      - Falls back to file counting if even sources list is unavailable
      - Returns UNKNOWN (not DOWN) when gbrain isn't installed
    """

    def _run(args, timeout=15):
        env = os.environ.copy()
        env["PATH"] = f"{Path.home() / '.bun/bin'}:{env.get('PATH', '')}"
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            env=env, cwd=str(Path.home() / "brain"),
        )

    def _parse_sources_list(output):
        """Parse page counts from 'gbrain sources list' output.

        Format:
          default               federated          1 pages  never synced
          my-source             isolated          12 pages  2m ago

        Known false positive: the 'default' federated source is auto-created
        by gbrain at install without a local_path and can never be synced.
        It is excluded from the 'never synced' / 'zero pages' counts.
        """
        lines = output.strip().split("\n")
        total = 0
        never_synced = 0
        zero_pages = 0
        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                pages = int(parts[2])
                if len(parts) >= 2 and parts[0] == "default" and parts[1] == "federated":
                    continue
                total += 1
                if pages == 0:
                    zero_pages += 1
                if "never synced" in line.lower():
                    never_synced += 1
        return total, never_synced, zero_pages

    try:
        bun_path = Path.home() / ".bun" / "bin"
        gbrain_cmd = str(bun_path / "gbrain")

        if not bun_path.exists() or not Path(gbrain_cmd).exists():
            return {"status": "UNKNOWN", "detail": "gbrain not installed — run install.sh"}

        # Try 1: gbrain doctor --json (authoritative)
        try:
            result = _run([gbrain_cmd, "doctor", "--json"], timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                import json as _json
                data = _json.loads(result.stdout)
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
                    detail = "; ".join(failures[:3])
                    more = f" (+{len(failures) - 3} more)" if len(failures) > 3 else ""
                    return {"status": "DEGRADED", "detail": f"{detail}{more}"}

                overall = data.get("overall_health_score", -1)
                if 0 <= overall < 50:
                    return {"status": "DEGRADED", "detail": f"Health score: {overall}/100"}
                return {"status": "UP", "detail": "All sources healthy"}
        except (json.JSONDecodeError, ValueError):
            pass  # Fall through to Try 2

        # Try 2: gbrain sources list (parseable fallback)
        result2 = _run([gbrain_cmd, "sources", "list"], timeout=15)
        if result2.returncode == 0 and result2.stdout.strip():
            total, never_synced, zero_pages = _parse_sources_list(result2.stdout)
            issues = []
            if never_synced > 0:
                issues.append(f"{never_synced} source(s) never synced")
            if zero_pages > 0 and zero_pages == total:
                issues.append("all sources have 0 pages")
            elif zero_pages > 0:
                issues.append(f"{zero_pages} source(s) have 0 pages")

            if issues:
                return {"status": "DEGRADED", "detail": "; ".join(issues[:2])}
            if total == 0:
                return {"status": "UNKNOWN", "detail": "no gbrain sources found"}
            return {"status": "UP", "detail": f"{total} source(s), all synced"}

        # Try 3: can't even list sources
        return {"status": "UNKNOWN", "detail": "gbrain available but sources list failed — run bootstrap-brain.sh"}

    except FileNotFoundError:
        return {"status": "UNKNOWN", "detail": "gbinary not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"status": "UNKNOWN", "detail": "gbrain check timed out"}
    except Exception as e:
        return {"status": "UNKNOWN", "detail": f"gbrain check: {e}"}


def check_inbox_staleness() -> dict:
    """Check if agent inbox was scanned recently (every 10m cron, warn if >25m stale)."""
    state_file = HERMES_HOME / "state" / "last-message-check"
    if not state_file.exists():
        return {"status": "DEGRADED", "detail": "No state file — check-agent-messages may not have run"}
    try:
        mtime = datetime.fromtimestamp(state_file.stat().st_mtime, tz=timezone.utc).astimezone()
        age = NOW - mtime
        if age < timedelta(minutes=15):
            return {"status": "UP", "detail": f"Last scan: {age.total_seconds() / 60:.0f}m ago"}
        elif age < timedelta(minutes=25):
            return {"status": "DEGRADED", "detail": f"Last scan: {age.total_seconds() / 60:.0f}m ago — may have missed a check"}
        else:
            return {"status": "DOWN", "detail": f"Last scan: {age.total_seconds() / 60:.0f}m ago — inbox polling may be stalled!"}
    except Exception as e:
        return {"status": "ERROR", "detail": f"Could not read state file: {e}"}


def _service_unit_exists(name: str) -> bool:
    """Check if a systemd unit file exists for the given service name.

    On Linux: checks /etc/systemd/system/, /usr/lib/systemd/system/,
    and ~/.config/systemd/user/ for the unit file.
    On macOS: returns True (launchctl doesn't need unit files).
    """
    if not _is_linux():
        return True  # macOS uses launchctl; no unit file check needed
    unit = name if name.endswith(".service") else f"{name}.service"
    search_paths = [
        os.path.expanduser("~/.config/systemd/user/"),
        "/etc/systemd/system/",
        "/usr/lib/systemd/system/",
    ]
    for prefix in search_paths:
        if os.path.isfile(os.path.join(prefix, unit)):
            return True
    return False


def run() -> str:
    """Run all checks and return report. Empty string = all healthy."""
    linux = _is_linux()

    if linux:
        ollama_service = "ollama"
        gbrain_service = "gbrain-autopilot"
    else:
        ollama_service = "com.ollama.serve"
        gbrain_service = "com.gbrain.autopilot"
        # Fallback to sync-watch if autopilot isn't running
        ap = check_service("com.gbrain.autopilot")
        if ap["status"] == "DOWN":
            gbrain_service = "com.gbrain.sync-watch"

    checks = {}

    # Check Ollama: only report DOWN if the service unit file exists
    if _service_unit_exists(ollama_service):
        checks["Ollama"] = check_service(ollama_service)
    else:
        checks["Ollama"] = {"status": "UP", "detail": "Skipped — not configured"}

    # Check gbrain: only report DOWN if the service unit file exists
    if _service_unit_exists(gbrain_service):
        checks["gbrain sync daemon"] = check_service(gbrain_service)
    else:
        checks["gbrain sync daemon"] = {"status": "UP", "detail": "Skipped — not configured"}

    checks.update({
        "gbrain sources": check_gbrain_sources(),
        "Docker (Langfuse)": check_docker_containers(),
        "Gateway activity": check_gateway_log(),
        "Agent inbox scan": check_inbox_staleness(),
        "Memory→brain sync": check_memory_sync_freshness(),
        "Disk usage": check_disk_usage(),
    })

    # Determine overall status
    status_counts = {"UP": 0, "DEGRADED": 0, "DOWN": 0, "ERROR": 0, "UNKNOWN": 0}
    for result in checks.values():
        s = result["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    overall = "HEALTHY"
    if status_counts.get("DOWN", 0) > 0:
        overall = "CRITICAL"
    elif status_counts.get("ERROR", 0) > 0:
        overall = "ERROR"
    elif status_counts.get("DEGRADED", 0) > 0:
        overall = "DEGRADED"

    # Build report
    now_str = NOW.strftime("%Y-%m-%d %H:%M:%S %Z")
    report = f"📡 Hermes Heartbeat — {now_str}\n"
    report += f"Overall: {overall}\n\n"

    icons = {"UP": "✅", "DEGRADED": "⚠️", "DOWN": "❌", "ERROR": "🔴", "UNKNOWN": "❓"}
    for name, result in checks.items():
        report += f"{icons.get(result['status'], '❓')} {name}: {result['status']} — {result['detail']}\n"

    # If overall healthy and not forced, return empty for silent cron
    if overall == "HEALTHY" and "--report" not in sys.argv:
        return ""

    return report


if __name__ == "__main__":
    output = run()
    if output:
        print(output)
        sys.exit(0 if "HEALTHY" in output else 1)
