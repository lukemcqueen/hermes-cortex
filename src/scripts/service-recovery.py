#!/usr/bin/env python3
"""
Service Recovery — self-healing daemon for critical services.
Checks each service; if down, attempts recovery.
Silent (empty output) when all services healthy.
Non-empty output is delivered to user as an incident report.
"""
from typing import Optional
import subprocess, sys, time, os
from pathlib import Path

UID = os.getuid()  # dynamic user ID
LANGFUSE_DIR = str(Path.home() / "langfuse")
HERMES_SCRIPTS = Path.home() / ".hermes" / "scripts"
CORTEX_SCRIPTS = Path.home() / "hermes-cortex" / "src" / "scripts"

SERVICES = [
    {
        "name": "nginx",
        "check": lambda: bool(subprocess.run(
            ["pgrep", "-f", "nginx: master"],
            capture_output=True, timeout=5).stdout.strip()),
        "restart_cmd": ["launchctl", "bootstrap",
                        f"gui/{UID}",
                        str(Path.home() / "Library/LaunchAgents/homebrew.mxcl.nginx.plist")],
        "fallback_cmd": ["nginx"],
        "verify_cmd": ["nginx", "-t"],
    },
    {
        "name": "Langfuse",
        "check": lambda: _check_docker("langfuse-langfuse-web"),
        "restart_cmd": ["docker", "compose", "up", "-d"],
        "restart_workdir": LANGFUSE_DIR,
        "verify_label": "langfuse-web container",
    },
    {
        "name": "Ollama",
        "check": lambda: _check_launchd("com.ollama.serve"),
        "restart_cmd": ["launchctl", "kickstart", f"gui/{UID}/com.ollama.serve"],
        "fallback_cmd": ["launchctl", "bootstrap", f"gui/{UID}",
                         str(Path.home() / "Library/LaunchAgents/com.ollama.serve.plist")],
        "verify_label": "Ollama server",
    },
    {
        "name": "gbrain",
        "check": lambda: (
            _check_launchd("com.gbrain.autopilot") or
            _check_launchd("com.gbrain.sync-watch")
        ),
        "restart_cmd": ["launchctl", "kickstart", f"gui/{UID}/com.gbrain.autopilot"],
        "fallback_cmd": ["launchctl", "bootstrap", f"gui/{UID}",
                         str(Path.home() / "Library/LaunchAgents/com.gbrain.sync-watch.plist")],
        "verify_label": "gbrain autopilot/sync-watch",
    },
    {
        "name": "scripts",
        "check": lambda: _check_scripts(),
        "restart_cmd": None,  # handled by _try_restore_scripts
        "verify_label": "Hermes scripts",
    },
]

# Keep track of recent restarts to prevent thrashing
_last_restart = {}  # service_name -> timestamp


def _check_docker(container_substring: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_substring}",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() != ""
    except Exception:
        return False


def _check_launchd(label: str) -> bool:
    """Check if a launchd service is running (has a PID)."""
    try:
        r = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return False
        # Check if there's a PID (first field in tab-separated output, or "PID" in plist format)
        if '"PID"' in r.stdout:
            import re
            m = re.search(r'"PID"\s*=\s*(\d+);', r.stdout)
            return m is not None and m.group(1) != "0"
        pid = r.stdout.split("\t")[0] if "\t" in r.stdout else "-"
        return pid != "-"
    except Exception:
        return False


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


def _try_restore_scripts() -> Optional[str]:
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


def _try_restart(svc: dict) -> Optional[str]:
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

    # Restart
    workdir = svc.get("restart_workdir")
    cmds = [svc["restart_cmd"]]
    if svc.get("fallback_cmd"):
        cmds.append(svc["fallback_cmd"])

    for idx, cmd in enumerate(cmds):
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                cwd=workdir or None,
            )
            if r.returncode == 0:
                break  # success on this attempt
            if idx < len(cmds) - 1:
                # Primary failed, try fallback
                continue
            return f"❌ {name} restart failed: {r.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return f"❌ {name} restart timed out (30s)"
        except Exception as e:
            return f"❌ {name} restart error: {e}"

    # Wait a moment then verify
    time.sleep(3)
    if svc["check"]():
        _last_restart[name] = now
        return None  # success
    else:
        return f"⚠️ {name} restart issued but service not confirmed up after 3s"


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
