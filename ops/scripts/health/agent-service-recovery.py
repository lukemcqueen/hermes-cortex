#!/usr/bin/env python3
"""
Service Recovery — self-healing daemon for critical services.
Checks each service; if down, attempts recovery.
Silent (empty output) when all services healthy.
Non-empty output is delivered to user as an incident report.
"""
import os
import subprocess
import sys
import time
import hashlib
import json
from pathlib import Path

# Ensure scripts dir is on Python path for sibling modules
_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in __import__('sys').path:
    __import__('sys').path.insert(0, str(_SCRIPT_DIR))

# Cross-platform service helpers
from platform_utils import (
    service_running,
    restart_service,
    docker_container_running,
    docker_available,
    is_macos,
    is_linux,
)
from state_tracker import StateTracker
from hermes_tz import format_timestamp

from datetime import datetime, timezone, timedelta

def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = format_timestamp("[%Y-%m-%d %H:%M %Z]")
    return f"{kst} {name}:"

UID = os.getuid()
LANGFUSE_DIR = str(Path.home() / "langfuse")
HERMES_SCRIPTS = Path.home() / ".hermes-cortex" / "scripts"
CORTEX_REPO_ENV = os.environ.get("CORTEX_REPO", "")

def _docker_via_sg(container: str) -> bool:
    """Check if a Docker container is running via sg docker -c (fallback when user not in docker group)."""
    try:
        r = subprocess.run(
            ["sg", "docker", "-c", f"docker ps --filter name={container} --format {{{{.Names}}}}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() != ""
    except Exception:
        return False

CORTEX_REPO_ENV = os.environ.get("CORTEX_REPO", "")
if CORTEX_REPO_ENV:
    CORTEX_SCRIPTS = Path(CORTEX_REPO_ENV) / "ops" / "scripts"
else:
    CORTEX_SCRIPTS = Path.home() / "hermes-cortex" / "ops" / "scripts"


def _make_service(name: str, label: str = "", pgrep: str = "",
                  docker_sub: str = "", restart_label: str = "",
                  verify_cmd: list | None = None) -> dict:
    """Factory: create a service config that works on macOS and Linux."""
    return {
        "name": name,
        "check": lambda lbl=label, pgr=pgrep, ds=docker_sub: (
            docker_container_running(ds) if ds else
            service_running(lbl, pgrep_pattern=pgr)
        ),
        "restart_label": restart_label or label or name,
        "verify_cmd": verify_cmd,
        "verify_label": name,
    }


# Keep track of recent restarts to prevent thrashing
_last_restart: dict[str, float] = {}


def _check_scripts() -> bool:
    """Check if critical Hermes scripts are present and executable."""
    critical = [
        "heartbeat.py", "agent-service-recovery.py", "agent-system-alert-watchdog.py",
        "cron-auto-remediate.sh",
    ]
    for name in critical:
        sp = HERMES_SCRIPTS / name
        if not sp.exists():
            return False
        if not os.access(str(sp), os.X_OK):
            return False
    return True


def _is_orchestrator() -> bool:
    """Check if this machine is an orchestrator (runs the Agent Bus server).
    
    Uses the same pattern as install.sh and cortex-update.sh:
    short hostname matched against moses|esther.
    """
    short = os.uname().nodename.split(".")[0].lower()
    return short in ("moses", "esther")


SERVICES: list[dict] = [
    _make_service("nginx", pgrep="nginx: master", restart_label="nginx.service", verify_cmd=["nginx", "-t"]),
    # Langfuse: Docker container
    {
        "name": "Langfuse",
        "check": lambda lbl="langfuse-langfuse-web": (
            docker_container_running(lbl)
            if docker_available()
            else _docker_via_sg(lbl)
        ),
        "restart_label": "langfuse-langfuse-web",
        "verify_label": "Langfuse",
    },
    _make_service("Ollama", label="ollama.service", pgrep="ollama"),
    # mycortex: DECOMMISSIONED 2026-08-02 (mycortex replaces) — service left
    # unregistered so the recovery loop never restarts a decommissioned daemon.
]
# cortex-bus: only on orchestrator machines (Moses/Esther). Non-orchestrators
# don't run the bus server and shouldn't try to recover it.
if _is_orchestrator():
    SERVICES.append(
        _make_service("cortex-bus", label="cortex-bus.service", pgrep="cortex-bus"),
    )
SERVICES.extend([
    {
        "name": "scripts",
        "check": _check_scripts,
        "restart_label": "",
        "verify_label": "Hermes scripts",
    },
])


def _try_restore_scripts() -> str | None:
    """Try to restore missing scripts from the cortex repo. Returns error or None."""
    restored = []
    critical = [
        "heartbeat.py", "agent-service-recovery.py", "agent-system-alert-watchdog.py",
        "cron-auto-remediate.sh",
        "daily-lesson-mine.sh", "update-session-state.sh",
        "agent-langfuse-health-watchdog.py", "agent-memory-to-brain-sync.py",
        "web-cache-backup.sh", "web-cache-prune.sh",
    ]
    for name in critical:
        target = HERMES_SCRIPTS / name
        source = CORTEX_SCRIPTS / name
        if not source.exists():
            # Search subdirectories (health/, manage/, etc.)
            for sub in sorted(CORTEX_SCRIPTS.rglob(name)):
                source = sub
                break
        if not target.exists() and source.exists():
            try:
                import shutil
                shutil.copy2(str(source), str(target))
                os.chmod(str(target), 0o755)
                restored.append(name)
            except Exception as e:
                return f"Failed to restore {name}: {e}"
    if restored:
        return None  # success
    return "No scripts needed restoration or cortex repo missing"


def _status_text(svc: dict) -> str:
    """Return a short status string for logging."""
    try:
        ok = svc["check"]()
        return "✅ up" if ok else "❌ DOWN"
    except Exception as e:
        return f"❓ error ({e})"


def _try_restart(svc: dict) -> str | None:
    """Attempt to restart a service. Returns error string or None on success."""
    name = svc["name"]
    now = time.time()

    # Anti-thrash: don't restart if we already tried in the last 5 minutes
    if name in _last_restart and (now - _last_restart[name]) < 300:
        return f"⚠️ {name} still down but was restarted {int(now - _last_restart[name])}s ago — throttled"

    # Run optional pre-flight verification
    verify = svc.get("verify_cmd")
    if verify:
        try:
            # Use sudo for nginx -t: cert files, error logs, and the 'user'
            # directive all require root-level access to validate.
            cmd = ["sudo"] + verify if name == "nginx" else verify
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return f"❌ {name}: pre-flight check failed ({r.stderr.strip()[:200]}) — not restarting"
        except FileNotFoundError:
            return f"❌ {name}: binary not found — skipping restart"

    # Restart using platform_utils with better error handling
    restart_label = svc.get("restart_label", name)
    if restart_label:
        try:
            # Docker containers need special handling
            if name == "Langfuse":
                r = subprocess.run(["sg", "docker", "-c",
                    f"docker compose -f {LANGFUSE_DIR}/docker-compose.yml restart langfuse-web"],
                    capture_output=True, text=True, timeout=30)
                ok = (r.returncode == 0)
            else:
                ok = restart_service(restart_label)
            if not ok:
                # Provide more detailed error information
                if is_macos():
                    return f"❌ {name} restart failed: service '{restart_label}' not found or permission denied. Try: launchctl list | grep {restart_label}"
                else:
                    return f"❌ {name} restart failed: service '{restart_label}' not found or permission denied. Try: sudo systemctl restart {restart_label}"
        except Exception as e:
            return f"❌ {name} restart failed with error: {str(e)}"

    # Wait a moment then verify
    time.sleep(3)
    if svc["check"]():
        _last_restart[name] = now
        return None
    else:
        return f"⚠️ {name} restart issued but not confirmed up after 3s"


def main():
    actions = []
    statuses = []

    for svc in SERVICES:
        name = svc["name"]
        try:
            running = svc["check"]()
        except Exception as e:
            statuses.append(f"{name}: error checking ({e})")
            continue

        if running:
            statuses.append(f"{name}: ✅ up")
            continue

        # Service is down — attempt recovery
        statuses.append(f"{name}: ❌ DOWN — recovering...")

        if name == "scripts":
            # Special handling: restore missing scripts from cortex repo
            err = _try_restore_scripts()
            if err:
                actions.append(f"❌ {name}: {err}")
            else:
                actions.append(f"🔄 {name}: restored missing scripts")
            continue

        err = _try_restart(svc)
        if err:
            actions.append(err)
        else:
            actions.append(f"🔄 {name}: restarted successfully")

    # State tracking — suppress duplicates, send resolution
    if actions:
        fp = "|".join(actions)
        st = StateTracker("service-recovery")
        action = st.evaluate(fp)

        if action == "silent":
            return  # same errors as last time

        from hermes_tz import format_timestamp
        hostname = os.uname().nodename[:12]
        ts = format_timestamp("%Y-%m-%d %H:%M %Z")
        print(f"[{ts}] service-recovery:")
        actions_line = "  " + "\n  ".join(actions)
        print(actions_line)
        for s in statuses:
            print(f"  {s}")
    else:
        # All services up — clear any prior error state
        st = StateTracker("service-recovery")
        st.evaluate("healthy", has_issues=False)

if __name__ == "__main__":
    main()
