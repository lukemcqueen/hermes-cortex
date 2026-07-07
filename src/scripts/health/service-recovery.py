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

# Cross-platform service helpers
from platform_utils import (
    service_running,
    restart_service,
    docker_container_running,
    is_macos,
    is_linux,
)
from state_tracker import StateTracker

from datetime import datetime, timezone, timedelta

def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = datetime.now(timezone(timedelta(hours=9))).strftime(
        "[%Y-%m-%d %H:%M KST]"
    )
    return f"{kst} {name}:"

UID = os.getuid()
LANGFUSE_DIR = str(Path.home() / "langfuse")
HERMES_SCRIPTS = Path.home() / ".hermes-cortex" / "scripts"
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
        "heartbeat.py", "service-recovery.py", "system-alert-watchdog.py",
        "orch-team-messages.sh", "cron-auto-remediate.sh",
    ]
    for name in critical:
        sp = HERMES_SCRIPTS / name
        if not sp.exists():
            return False
        if not os.access(str(sp), os.X_OK):
            return False
    return True


SERVICES: list[dict] = [
    _make_service("nginx", pgrep="nginx: master", restart_label="homebrew.mxcl.nginx", verify_cmd=["nginx", "-t"]),
    # Langfuse: try multiple label formats for compatibility
    {
        "name": "Langfuse",
        "check": lambda lbl="langfuse-langfuse-web": (
            docker_container_running(lbl) if lbl else False
        ),
        "restart_label": "langfuse-langfuse-web",
        "verify_label": "Langfuse",
    },
    _make_service("Ollama", label="com.ollama.serve", pgrep="ollama"),
    # gbrain: systemd user service (not Docker — don't check Docker)
    _make_service("gbrain", label="gbrain-autopilot", pgrep="gbrain"),
    {
        "name": "scripts",
        "check": _check_scripts,
        "restart_label": "",
        "verify_label": "Hermes scripts",
    },
]


def _try_restore_scripts() -> str | None:
    """Try to restore missing scripts from the cortex repo. Returns error or None."""
    restored = []
    critical = [
        "heartbeat.py", "service-recovery.py", "system-alert-watchdog.py",
        "orch-team-messages.sh", "cron-auto-remediate.sh",
        "daily-lesson-mine.sh", "update-session-state.sh",
        "langfuse-health-watchdog.py", "memory-to-brain-sync.py",
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
            r = subprocess.run(verify, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return f"❌ {name}: pre-flight check failed ({r.stderr.strip()[:200]}) — not restarting"
        except FileNotFoundError:
            return f"❌ {name}: binary not found — skipping restart"

    # Restart using platform_utils with better error handling
    restart_label = svc.get("restart_label", name)
    if restart_label:
        try:
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


def _fix_gbrain_stale_lock() -> str | None:
    """Check and remove stale gbrain autopilot lock file. Returns message or None."""
    lock = Path.home() / ".gbrain" / "autopilot.lock"
    if not lock.exists():
        return None
    try:
        pid_str = lock.read_text().strip()
        if not pid_str.isdigit():
            lock.unlink()
            return "removed corrupt lock file"
        pid = int(pid_str)
        # Check if PID is alive
        alive = subprocess.run(
            ["kill", "-0", str(pid)], capture_output=True, timeout=5
        ).returncode == 0
        if not alive:
            lock.unlink()
            return f"removed stale lock (PID {pid} dead)"
        return None  # lock is valid, don't touch it
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return f"lock check error: {e}"


def _fix_gbrain_orphan_process() -> str | None:
    """Detect and kill gbrain autopilot running outside systemd.

    If a bun/raw gbrain autopilot process is found but the systemd service
    is not running, kill the orphan and return a message.
    Returns None if no orphan is found.
    Triggers systemd restart via the caller's normal restart flow.
    """
    # Only applies on Linux
    if not is_linux():
        return None
    # Check if systemd service is already active
    out, _, rc = _run(["systemctl", "--user", "is-active", "gbrain-autopilot"])
    if rc == 0 and out.strip() == "active":
        return None  # systemd is managing it — nothing to fix
    # Look for orphan bun/raw gbrain autopilot processes
    out, _, _ = _run(["pgrep", "-f", r"bun.*gbrain.*autopilot|gbrain.*autopilot"])
    if not out.strip():
        return None  # no raw process found
    pids = out.strip().split()
    killed = []
    for pid in pids:
        # Check this isn't the systemd-managed PID
        sysd_pid, _, _ = _run(["systemctl", "--user", "show", "-p", "MainPID", "gbrain-autopilot"])
        if sysd_pid.strip() and sysd_pid.strip() != "0":
            sp = sysd_pid.split("=")[-1]
            if pid == sp:
                continue  # this IS the systemd-managed PID
        _run(["kill", "-TERM", pid])
        import time
        for _ in range(3):
            alive, _, _ = _run(["kill", "-0", pid])
            if alive != 0:
                break
            time.sleep(1)
        alive_check, _, _ = _run(["kill", "-0", pid])
        if alive_check == 0:
            _run(["kill", "-KILL", pid])
            killed.append(f"{pid}(SIGKILL)")
        else:
            killed.append(f"{pid}(TERM)")
    if killed:
        return f"killed orphan autopilot process(es): {', '.join(killed)}"
    return None


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

        if name == "gbrain":
            # Stale lock file can prevent restart even after service appears down
            lock_msg = _fix_gbrain_stale_lock()
            if lock_msg:
                actions.append(f"🔧 gbrain: {lock_msg}")
            # Detect and kill orphan bun processes running outside systemd
            orphan_msg = _fix_gbrain_orphan_process()
            if orphan_msg:
                actions.append(f"🔧 gbrain: {orphan_msg}")
            # Proceed with restart regardless — locks cleared, orphans dead

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
