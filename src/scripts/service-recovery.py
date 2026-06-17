#!/usr/bin/env python3
"""
Service Recovery — self-healing daemon for critical services.
Checks each service; if down, attempts recovery.
Silent (empty output) when all services healthy.
Non-empty output is delivered to user as an incident report.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import hashlib
import json
from pathlib import Path

# Cross-platform service helpers
from platform_utils import (
    service_running,
    restart_service,
    docker_container_running,
    is_macos,
    is_linux,
)

UID = os.getuid()
LANGFUSE_DIR = str(Path.home() / "langfuse")
HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
CORTEX_REPO_ENV = os.environ.get("CORTEX_REPO", "")
if CORTEX_REPO_ENV:
    CORTEX_SCRIPTS = Path(CORTEX_REPO_ENV) / "src" / "scripts"
else:
    CORTEX_SCRIPTS = Path.home() / "hermes-cortex" / "src" / "scripts"


def _make_service(name: str, label: str = "", pgrep: str = "",
                  docker_sub: str = "", restart_label: str = "",
                  verify_cmd: list | None = None) -> dict:
    """Factory: create a service config that works on macOS and Linux."""
    return {
        "name": name,
        "check": lambda lbl=label, pgr=pgrep, ds=docker_sub: (
            docker_container_running(ds) if ds else
            service_running(lbl, pgrep_pattern=pgr if not lbl else None)
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
        "heartbeat.py", "service-recovery.py", "system-alert.py",
        "check-agent-messages.sh", "cron-auto-remediate.sh",
    ]
    for name in critical:
        sp = HERMES_SCRIPTS / name
        if not sp.exists():
            return False
        if not os.access(str(sp), os.X_OK):
            return False
    return True


def _try_restore_scripts() -> str | None:
    """Try to restore missing scripts from the cortex repo. Returns error or None."""
    restored = []
    critical = [
        "heartbeat.py", "service-recovery.py", "system-alert.py",
        "check-agent-messages.sh", "cron-auto-remediate.sh",
        "daily-lesson-mine.sh", "update-session-state.sh",
        "langfuse-health-watchdog.py", "memory-to-brain.py",
        "web-cache-backup.sh", "web-cache-prune.sh",
    ]
    for name in critical:
        target = HERMES_SCRIPTS / name
        source = CORTEX_SCRIPTS / name
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


SERVICES: list[dict] = [
    _make_service("nginx", pgrep="nginx: master",
                  restart_label="homebrew.mxcl.nginx",
                  verify_cmd=["nginx", "-t"]),
    _make_service("Langfuse", docker_sub="langfuse-langfuse-web"),
    _make_service("Ollama", label="com.ollama.serve", pgrep="ollama"),
    _make_service("gbrain", label="com.gbrain.autopilot",
                  pgrep="gbrain"),
    {
        "name": "scripts",
        "check": _check_scripts,
        "restart_label": "",
        "verify_label": "Hermes scripts",
    },
]


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
        r = subprocess.run(verify, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return f"❌ {name}: pre-flight check failed ({r.stderr.strip()[:200]}) — not restarting"

    # Restart using platform_utils
    restart_label = svc.get("restart_label", name)
    if restart_label:
        ok = restart_service(restart_label)
        if not ok:
            return f"❌ {name} restart failed (platform_utils returned False)"

    # Wait a moment then verify
    time.sleep(3)
    if svc["check"]():
        _last_restart[name] = now
        return None
    else:
        return f"⚠️ {name} restart issued but not confirmed up after 3s"


def _status_text(svc: dict) -> str:
    """Return a short status string for logging."""
    try:
        ok = svc["check"]()
        return "✅ up" if ok else "❌ DOWN"
    except Exception as e:
        return f"❓ error ({e})"


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

    if actions:
        hostname = os.uname().nodename[:12]
        print(f"🔧 {hostname}")
        for a in actions:
            print(a)
        for s in statuses:
            print(f"  {s}")


if __name__ == "__main__":
    main()
