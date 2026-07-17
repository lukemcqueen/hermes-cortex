"""platform_utils.py — Cross-platform helpers for Hermes Cortex scripts.

Provides macOS/Linux service management, HTTP checks, Docker detection,
and platform detection. All functions return simple booleans or None
so they can be used as drop-in replacements in both shell and Python contexts.

Usage:
    from platform_utils import service_running, http_ok, docker_running, is_macos
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ── Platform detection ──────────────────────────────────────────

def is_macos() -> bool:
    """True if running on macOS."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """True if running on Linux."""
    return sys.platform == "linux"


def platform_name() -> str:
    """Return 'macos', 'linux', or 'unknown'."""
    if is_macos():
        return "macos"
    elif is_linux():
        return "linux"
    return "unknown"


# ── Service management ──────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    """Run a command, return (stdout, stderr, rc)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", "command not found", -1
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def service_running(label: str, pgrep_pattern: "Optional[str]" = None) -> bool:
    """Check if a service is running.

    On macOS: checks via launchctl list.
    On Linux: checks via systemctl --user is-active, falls back to pgrep.
    If pgrep_pattern is provided, also tries pgrep as a fallback.

    Returns True if the service appears to be running.
    """
    if is_macos():
        out, _, rc = _run(["launchctl", "list", label])
        if rc == 0 and out:
            # macOS 12+ outputs plist-style dict
            m = re.search(r'"PID"\s*=\s*(\d+)', out)
            if m and m.group(1) != "0":
                return True
            # Tabular fallback
            pid = out.split("\t")[0] if "\t" in out else "-"
            if pid != "-":
                return True
        # Fallback to pgrep
        if pgrep_pattern:
            out, _, _ = _run(["pgrep", "-f", pgrep_pattern])
            return bool(out.strip())
        return False

    elif is_linux():
        # Try systemd user service first
        out, _, rc = _run(["systemctl", "--user", "is-active", label])
        if rc == 0 and out.strip() == "active":
            return True
        # Try systemd system service
        out, _, rc = _run(["systemctl", "is-active", label])
        if rc == 0 and out.strip() == "active":
            return True
        # Fallback to pgrep
        if pgrep_pattern:
            out, _, _ = _run(["pgrep", "-f", pgrep_pattern])
            return bool(out.strip())
        return False

    return False


def restart_service(label: str) -> bool:
    """Restart a service. Returns True on success.

    On macOS: launchctl kickstart.
    On Linux: systemctl --user restart, fallback to systemctl restart.
    """
    if is_macos():
        _, _, rc = _run(["launchctl", "kickstart", f"gui/{os.getuid()}/{label}"])
        if rc != 0:
            # Try bootstrap as fallback
            plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            if plist.exists():
                _, _, rc = _run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)])
        return rc == 0

    elif is_linux():
        _, _, rc = _run(["systemctl", "--user", "restart", label])
        if rc != 0:
            _, _, rc = _run(["sudo", "systemctl", "restart", label])
        return rc == 0

    return False


# ── HTTP checks ─────────────────────────────────────────────────

def http_ok(url: str, timeout: int = 5) -> bool:
    """Check if a URL returns HTTP 2xx."""
    try:
        import urllib.request
        r = urllib.request.urlopen(url, timeout=timeout)
        return 200 <= r.status < 300
    except Exception:
        return False


# ── Docker checks ───────────────────────────────────────────────

def docker_available() -> bool:
    """Check if Docker daemon is running and accessible."""
    try:
        r = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def docker_container_running(container_substring: str) -> bool:
    """Check if a Docker container with the given name substring is running."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_substring}",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() != ""
    except Exception:
        return False


# ── Process checks ──────────────────────────────────────────────

def pgrep_running(pattern: str) -> bool:
    """Check if a process matching the pattern is running."""
    out, _, _ = _run(["pgrep", "-f", pattern])
    return bool(out.strip())


# ── Cert expiry ─────────────────────────────────────────────────

def cert_expiry_days(cert_path: str) -> "Optional[int]":
    """Return days until certificate expiry, or None if unreadable."""
    from datetime import datetime, timezone
    out, _, rc = _run(
        ["openssl", "x509", "-in", cert_path, "-noout", "-enddate"]
    )
    if rc != 0 or not out.strip():
        return None
    try:
        expiry_str = out.split("=", 1)[1].strip()
        # Strip trailing timezone name
        for tz in [" GMT", " UTC", " EST", " EDT", " PST", " PDT"]:
            if expiry_str.endswith(tz):
                expiry_str = expiry_str[:-len(tz)]
                break
        expiry = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y")
        expiry = expiry.replace(tzinfo=timezone.utc)
        return (expiry - datetime.now(timezone.utc)).days
    except (ValueError, IndexError):
        return None