#!/usr/bin/env python3
"""
system-alert-watchdog.py — System health + resource watchdog (merged heartbeat).

Silent (empty stdout) when all metrics within normal range.
Non-empty stdout is delivered verbatim to the user (Telegram).
Supports Linux and macOS.

Checks:
  - Resource thresholds (memory, swap, disk, load)
  - Ollama, gbrain, Langfuse Docker services
  - Gateway activity, inbox scan freshness, memory→brain sync freshness
  - Loop governance DB health
  - Auto-remediation: purge, brew cleanup, docker prune, old logs
"""
import json as _json
import os
import re
import subprocess
import sys
import socket
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
PARENT_DIR = SCRIPT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
from hermes_tz import format_timestamp
from state_tracker import StateTracker
from hermes_models import load_models_env

_MODELS_ENV = load_models_env()
_EMBEDDING_MODEL = _MODELS_ENV.get("EMBEDDING_MODEL", "nomic-embed-text:v1.5")

MEM_PCT_WARN = 85
SWAP_PCT_WARN = 95
DISK_PCT_WARN = 90

alerts = []
details = []
remediations = []
HOSTNAME = socket.gethostname()[:12]
NOW = datetime.now().astimezone()

def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = datetime.now(timezone(timedelta(hours=9))).strftime(
        "[%Y-%m-%d %H:%M KST]"
    )
    return f"{kst} {name}:"
CORTEX_DEPLOY_HOME = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex"))
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
BRAIN_SHARED = Path.home() / "brain" / "shared"

# ── Helpers ──────────────────────────────────────────────

def safe_hostname() -> str:
    return "server"

def scrub_pii(text: str) -> str:
    home = str(Path.home())
    return text.replace(home, "~")

is_linux = sys.platform.startswith("linux")
is_macos = sys.platform == "darwin"

def _is_linux() -> bool:
    global is_linux
    return is_linux

# ── Service checks (from heartbeat.py) ──────────────────

def check_systemd(unit_name: str) -> dict:
    for scope, label in [(["--user"], "user"), ([], "system")]:
        try:
            # systemctl --user needs DBUS_SESSION_BUS_ADDRESS + XDG_RUNTIME_DIR
            # which cron/terminal environments may not have
            env = os.environ.copy()
            if scope == ["--user"]:
                uid = os.getuid()
                env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
                env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
            result = subprocess.run(
                ["systemctl", *scope, "is-active", unit_name],
                capture_output=True, text=True, timeout=10, env=env,
            )
            status = result.stdout.strip()
            if result.returncode == 0 and status == "active":
                return {"status": "UP", "detail": f"{unit_name} ({label})"}
            if result.returncode != 0 and status in ("inactive", "dead", "failed"):
                continue
            if result.returncode == 0:
                return {"status": "UP", "detail": f"{unit_name} ({label})"}
        except FileNotFoundError:
            return {"status": "ERROR", "detail": "systemctl not found"}
        except Exception as e:
            return {"status": "ERROR", "detail": str(e)}
    try:
        proc_name = unit_name.split(".")[-1] if "." in unit_name else unit_name
        pg = subprocess.run(["pgrep", "-x", proc_name], capture_output=True, timeout=5)
        if pg.returncode == 0:
            return {"status": "DEGRADED", "detail": f"{unit_name} (process found, no systemd unit)"}
        # Fuzzy fallback: split unit name on hyphens/dots (e.g. "gbrain-autopilot" -> "gbrain.*autopilot")
        # catches processes launched via interpreters (bun, python, java) whose process name is the interpreter
        parts = re.split(r"[-.]+", unit_name)
        if len(parts) > 1:
            fuzzy = ".*".join(parts)
            pg = subprocess.run(["pgrep", "-f", fuzzy], capture_output=True, timeout=5)
            if pg.returncode == 0:
                pids = pg.stdout.decode().strip().split()
                return {"status": "DEGRADED", "detail": f"{unit_name} (fuzzy pgrep '{fuzzy}', PID(s) {'/'.join(pids)})"}
    except Exception:
        pass
    return {"status": "DOWN", "detail": f"{unit_name} not active in any scope"}

def _check_launchd(job_label: str) -> dict:
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
            if exit_code not in (0, 256):
                # Exit code 9 (SIGKILL) is normal when launched with --replace
                # — the old process is intentionally killed during replacement.
                # The current process is alive (has PID), so this is a false positive.
                if exit_code == 9:
                    return {"status": "UP", "detail": f"PID {pid} (previous instance cleanly replaced, LastExitStatus=9 expected with --replace)"}
                proc_name = job_label.split(".")[-1]
                pg = subprocess.run(["pgrep", "-xf", f".*{proc_name}.*"], capture_output=True, timeout=5)
                if pg.returncode == 0:
                    return {"status": "DEGRADED", "detail": f"PID {pid}, process alive but LastExitStatus={exit_code}"}
                return {"status": "DEGRADED", "detail": f"PID {pid}, but LastExitStatus={exit_code} and process not found"}
            return {"status": "UP", "detail": f"PID {pid}"}
        proc_name = job_label.split(".")[-1]
        pg = subprocess.run(["pgrep", "-x", proc_name], capture_output=True, timeout=5)
        if pg.returncode != 0:
            for component in reversed(job_label.split(".")):
                if component == proc_name:
                    continue
                pg = subprocess.run(["pgrep", "-f", component], capture_output=True, timeout=5)
                if pg.returncode == 0:
                    break
        if pg.returncode == 0:
            pids = pg.stdout.decode().strip().split()
            return {"status": "UP", "detail": f"Running outside launchd (PID {'/'.join(pids)})"}
        return {"status": "DOWN", "detail": f"No PID in launchd, and '{proc_name}' not found via pgrep"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}

def check_service(label: str) -> dict:
    if is_linux:
        return check_systemd(label)
    return _check_launchd(label)

def check_docker_containers() -> dict:
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

def check_gateway_log() -> dict:
    """Check Hermes gateway health — platform-aware.

    On Linux: check systemd service + journald activity.
    On macOS: check launchd job (ai.hermes.gateway).

    The old approach of checking ~/.hermes-cortex/logs/*.log caused
    false-positive alerts because that directory only contains the
    cortex-dashboard log (a separate local Flask server).
    """
    if is_linux:
        # Linux: systemd + journald
        svc_check = check_systemd("hermes-gateway")
        if svc_check["status"] in ("DOWN", "ERROR"):
            return {"status": "DOWN", "detail": f"Gateway service: {svc_check['detail']}"}
        try:
            result = subprocess.run(
                ["journalctl", "--user", "-u", "hermes-gateway",
                 "--since", "10 minutes ago", "--no-pager", "-n", "3"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                return {"status": "UP", "detail": "Running, activity in last 10 min (journald)"}
            return {"status": "UP", "detail": f"Running (service: {svc_check['detail']})"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"status": "UP", "detail": f"Running (service: {svc_check['detail']})"}

    # macOS: check launchd (ai.hermes.gateway)
    return _check_launchd("ai.hermes.gateway")

def check_memory_sync_freshness() -> dict:
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
    """Check gbrain autopilot is running. Avoids DB-lock contention with running autopilot."""
    try:
        bun_path = Path.home() / ".bun" / "bin"
        gbrain_cmd = str(bun_path / "gbrain")
        if not bun_path.exists() or not Path(gbrain_cmd).exists():
            return {"status": "UNKNOWN", "detail": "gbrain not installed"}
        # Check autopilot process directly via pgrep — no DB lock needed
        pg = subprocess.run(
            ["pgrep", "-f", "gbrain.*autopilot"],
            capture_output=True, timeout=5,
        )
        if pg.returncode != 0:
            return {"status": "DOWN", "detail": "gbrain-autopilot not active in any scope"}
        pids = pg.stdout.decode().strip().split()
        # Verify autopilot log is recent (last 10 min)
        log = Path.home() / ".gbrain" / "autopilot.log"
        log_ok = True
        if log.exists():
            age = (NOW - datetime.fromtimestamp(log.stat().st_mtime, tz=timezone.utc).astimezone()).total_seconds()
            if age > 600:
                # Log stale — check journald (autopilot may log via systemd, not to file)
                try:
                    jctl = subprocess.run(
                        ["journalctl", "--user", "-u", "gbrain-autopilot.service",
                         "--since", "10 minutes ago", "--no-pager", "-n", "5"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if jctl.returncode == 0 and jctl.stdout.strip():
                        log_ok = True  # Journald has recent activity
                    else:
                        log_ok = False
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    log_ok = False
                if not log_ok:
                    return {"status": "DEGRADED", "detail": f"autopilot PID(s) {'/'.join(pids)} but log stale ({age:.0f}s)"}
        return {"status": "UP", "detail": f"autopilot PID(s) {'/'.join(pids)}"}
    except FileNotFoundError:
        return {"status": "UNKNOWN", "detail": "pgrep not found"}
    except subprocess.TimeoutExpired:
        return {"status": "UNKNOWN", "detail": "autopilot check timed out"}
    except Exception as e:
        return {"status": "UNKNOWN", "detail": f"gbrain check: {e}"}

# ── Legacy resource checks (from original system-alert-watchdog.py) ──

def check_resources():
    """Memory, swap, load, disk with auto-remediation."""
    # Memory & Swap
    try:
        if is_linux:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            def _kv(key):
                m = re.search(rf"^{key}:\s+(\d+)", meminfo, re.MULTILINE)
                return int(m.group(1)) * 1024 if m else 0
            total_b = _kv("MemTotal")
            free_b = _kv("MemFree")
            avail_b = _kv("MemAvailable")
            total_mb = round(total_b / 1048576, 1)
            used_mb = round((total_b - avail_b) / 1048576, 1)
            avail_mb = round(avail_b / 1048576, 1)
            pct = round(used_mb / total_mb * 100, 1) if total_mb else 0
            details.append(f"Memory: {pct}% ({used_mb}MB used, {avail_mb}MB available / {total_mb}MB total)")
            if pct > MEM_PCT_WARN:
                alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")
            swap_total_b = _kv("SwapTotal")
            swap_free_b = _kv("SwapFree")
            swap_cached_b = _kv("SwapCached")
            swap_used_b = swap_total_b - swap_free_b
            swap_pct = round(swap_used_b / swap_total_b * 100, 1) if swap_total_b else 0
            if swap_total_b:
                details.append(f"Swap: {swap_pct}% ({round(swap_used_b/1048576,1)}MB / {round(swap_total_b/1048576,1)}MB)")
                if swap_pct > SWAP_PCT_WARN:
                    alerts.append(f"⚠️ Swap at {swap_pct}% — exceeds {SWAP_PCT_WARN}% threshold")
        elif is_macos:
            page_size = 4096
            tr = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
            def _vm_val(key, text):
                m = re.search(rf'^{key}:\s+([\d.]+)\.', text, re.MULTILINE)
                return int(m.group(1)) if m else 0
            free_pg = _vm_val("Pages free", tr.stdout)
            active_pg = _vm_val("Pages active", tr.stdout)
            inactive_pg = _vm_val("Pages inactive", tr.stdout)
            wired_pg = _vm_val("Pages wired down", tr.stdout)
            tr2 = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            total_bytes = int(tr2.stdout.strip())
            total_mb = round(total_bytes / 1048576, 1)
            used_mb = round((active_pg + wired_pg) * page_size / 1048576, 1)
            avail_mb = round((free_pg + inactive_pg) * page_size / 1048576, 1)
            pct = round(used_mb / total_mb * 100, 1) if total_mb else 0
            details.append(f"Memory: {pct}% ({used_mb}MB used + {avail_mb}MB available / {total_mb}MB total)")
            if pct > MEM_PCT_WARN:
                alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")
                try:
                    subprocess.run(["purge"], capture_output=True, timeout=30)
                    remediations.append("🔄 Ran purge to free inactive memory")
                except Exception:
                    pass
            r = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5)
            parts = r.stdout.strip().replace("=", "").split()
            if len(parts) > 3:
                s_total = float(parts[1].rstrip("M"))
                s_used = float(parts[3].rstrip("M"))
                s_pct = round(s_used / s_total * 100, 1) if s_total else 0
                details.append(f"Swap: {s_pct}% ({s_used}MB / {s_total}MB)")
                if s_pct > SWAP_PCT_WARN:
                    alerts.append(f"⚠️ Swap at {s_pct}% — exceeds {SWAP_PCT_WARN}% threshold")
    except Exception as e:
        details.append(f"Memory: error ({e})")

    # Load average
    try:
        if is_linux:
            with open("/proc/loadavg") as f:
                parts = f.read().strip().split()[:3]
        elif is_macos:
            r = subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True, timeout=5)
            parts = r.stdout.strip().strip("{}").split()[:3]
        else:
            parts = []
        if len(parts) >= 3:
            details.append(f"Load: {parts[0]} / {parts[1]} / {parts[2]}")
    except Exception:
        pass

    # Disk (with auto-remediation)
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            for p in parts:
                if p.endswith("%"):
                    pct = int(p.rstrip("%"))
                    used_str = parts[2] if len(parts) > 2 else "?"
                    total_str = parts[1] if len(parts) > 1 else "?"
                    details.append(f"Disk: {pct}% ({used_str} / {total_str})")
                    if pct > DISK_PCT_WARN:
                        alerts.append(f"⚠️ Disk at {pct}% — exceeds {DISK_PCT_WARN}% threshold")
                        if is_macos:
                            try:
                                subprocess.run(["brew", "cleanup", "-s"], capture_output=True, timeout=120)
                                remediations.append("🔄 Ran brew cleanup -s")
                            except Exception:
                                pass
                        elif is_linux:
                            try:
                                subprocess.run(["sudo", "apt", "autoremove", "--purge", "-y"], capture_output=True, timeout=120)
                                remediations.append("🔄 Ran apt autoremove")
                            except Exception:
                                pass
                            try:
                                subprocess.run(["sudo", "apt", "clean"], capture_output=True, timeout=30)
                                remediations.append("🔄 Ran apt clean")
                            except Exception:
                                pass
                        try:
                            subprocess.run(["docker", "system", "prune", "-f"], capture_output=True, timeout=60)
                            remediations.append("🔄 Ran docker system prune")
                        except Exception:
                            pass
                        subprocess.run(
                            ["find", str(Path.home() / ".hermes/logs"), "-name", "*.log*", "-mtime", "+7", "-delete"],
                            capture_output=True, timeout=30)
                    break
    except Exception:
        details.append("Disk: error reading")

# ── Loop Governance Health ──────────────────────────────

def check_loop_gov():
    LOOP_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
    try:
        ollama_up = False
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                tags = _json.loads(resp.read())
                ollama_up = True
                models = [m["name"] for m in tags.get("models", [])]
                if not any(_EMBEDDING_MODEL in m for m in models):
                    alerts.append(f"⚠️ {_EMBEDDING_MODEL} model not pulled — run: ollama pull {_EMBEDDING_MODEL}")
                    details.append(f"  Run: ollama pull {_EMBEDDING_MODEL}")
        except Exception as e:
            alerts.append(f"⚠️ Ollama check error: {e}")
            details.append("  Attempting auto-restart…")
            try:
                subprocess.run(["ollama", "serve"], capture_output=True, timeout=5)
                details.append("  → ollama serve started")
            except Exception:
                details.append("  → auto-restart failed (try: ollama serve &)")
        if LOOP_DB.exists():
            size_mb = round(LOOP_DB.stat().st_size / 1048576, 1)
            details.append(f"Loop DB: {size_mb}MB")
            if size_mb > 100:
                alerts.append(f"⚠️ Loop DB at {size_mb}MB — run vacuum_old_cycles(days=90)")
        else:
            details.append("Loop DB: not yet created")
        import sqlite3
        try:
            conn = sqlite3.connect(str(LOOP_DB))
            count = conn.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
            conn.close()
            details.append(f"Scored cycles: {count}")
        except Exception:
            pass
    except Exception as e:
        details.append(f"Loop governance: error ({e})")

# ── Main ────────────────────────────────────────────────

def main():
    # Phase 1: Resource threshold checks (with auto-remediation)
    check_resources()

    # Phase 2: Service availability checks
    if is_linux:
        ollama_svc = "ollama"
        gbrain_svc = "gbrain-autopilot"
    else:
        ollama_svc = "com.ollama.serve"
        gbrain_svc = "com.gbrain.autopilot"

    services = {
        "Ollama": check_service(ollama_svc),
        "gbrain sync": check_service(gbrain_svc),
        "gbrain sources": check_gbrain_sources(),
        "Docker (Langfuse)": check_docker_containers(),
        "Gateway activity": check_gateway_log(),
        "Memory→brain sync": check_memory_sync_freshness(),
    }

    icons = {"UP": "✅", "DEGRADED": "⚠️", "DOWN": "❌", "ERROR": "🔴", "UNKNOWN": "❓"}

    # Add service statuses to details/alerts
    for name, result in services.items():
        s = result["status"]
        detail_str = result["detail"]
        if s == "UP":
            details.append(f"{name}: UP — {detail_str}")
        elif s == "DEGRADED":
            alerts.append(f"⚠️ {name}: {detail_str}")
            details.append(f"{name}: {s} — {detail_str}")
        elif s in ("DOWN", "ERROR"):
            alerts.append(f"❌ {name}: {detail_str}")
            details.append(f"{name}: {s} — {detail_str}")
        else:
            details.append(f"{name}: {s} — {detail_str}")

    # Phase 3: Loop governance health
    check_loop_gov()

    # ── Output ──
    if not alerts:
        # Healthy — clear any prior error state
        st = StateTracker("system-alert")
        st.evaluate("healthy", has_issues=False)
        return  # silent

    # Build state fingerprint from alerts
    output_parts = [_cron_ts("system-alert-watchdog")]

    for a in alerts:
        output_parts.append(a)

    if remediations:
        output_parts.append("")
        output_parts.append("🛠️ Auto-remediation applied:")
        for r in remediations:
            output_parts.append(f"  {r}")

    if not alerts:
        output_parts.append("✅ All systems nominal")

    output_parts.append("")
    output_parts.append("── Details ──")
    for d in details:
        output_parts.append(f"  {d}")

    output_parts.append("")

    # Track state — prevent duplicate alerts
    st = StateTracker("system-alert")
    st.evaluate("\n".join(output_parts), has_issues=True)

    print("\n".join(output_parts))

if __name__ == "__main__":
    main()
