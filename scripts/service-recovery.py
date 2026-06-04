#!/usr/bin/env python3
"""
Service Recovery — self-healing daemon for critical services.
Checks each service; if down, attempts recovery.
Silent (empty output) when all services healthy.
Non-empty output is delivered to user as an incident report.
"""
import subprocess, sys, time, os
from pathlib import Path

UID = 501  # luke's user ID
LANGFUSE_DIR = str(Path.home() / "langfuse")

SERVICES = [
    {
        "name": "nginx",
        "check": lambda: bool(subprocess.run(
            ["pgrep", "-f", "nginx: master"],
            capture_output=True, timeout=5).stdout.strip()),
        "restart_cmd": ["launchctl", "bootstrap",
                        f"gui/{UID}",
                        str(Path.home() / "Library/LaunchAgents/homebrew.mxcl.nginx.plist")],
        "fallback_cmd": ["/usr/local/opt/nginx/bin/nginx"],
        "verify_cmd": ["/usr/local/bin/nginx", "-t"],
    },
    {
        "name": "Langfuse",
        "check": lambda: _check_docker("langfuse-langfuse-web"),
        "restart_cmd": ["docker", "compose", "up", "-d"],
        "restart_workdir": LANGFUSE_DIR,
        "verify_label": "langfuse-web container",
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
        err = _try_restart(svc)
        if err:
            actions.append(err)
        else:
            actions.append(f"🔄 {name}: restarted successfully")

    if actions:
        hostname = os.uname().nodename
        print(f"🔧 *Service Recovery — {hostname}*")
        print()
        for a in actions:
            print(a)
        print()
        print("── Current Status ──")
        for s in statuses:
            print(f"  {s}")


if __name__ == "__main__":
    main()
