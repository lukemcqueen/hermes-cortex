#!/usr/bin/env python3
"""Generate and deploy blocked_ips.conf for nginx.

Single sudo invocation handles the full lifecycle:
  Read blocked_ips.add → validate IPs → write .new config → atomic rename → nginx -t → nginx -s reload

Run as root (via sudo) for the full deploy:
  sudo /path/to/fix-blocked-ips.py

Run without sudo to only generate the config to /tmp/ (legacy mode for scripts that
handle the deploy themselves):
  python3 /path/to/fix-blocked-ips.py

Install sudoers rule:
  echo '$USER ALL=(root) NOPASSWD: $HOME/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py' | \
    sudo tee /etc/sudoers.d/moses
"""
import os
import re
import signal
import subprocess
import sys
import time

# ── Constants ──
IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$")
# CIDR_PREFIX_RE strips the /NN suffix for validation
CIDR_PREFIX_RE = re.compile(r"^(.*?)(?:/\d{1,2})?$")
PRIVATE_RANGES = re.compile(
    r"^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|0\.|169\.254\.|224\.|240\.)"
)

# Platform-aware nginx paths
# Linux: /usr/sbin/nginx, /etc/nginx
# macOS x86_64: /usr/local/bin/nginx, /usr/local/etc/nginx
# macOS arm64: /opt/homebrew/bin/nginx, /opt/homebrew/etc/nginx
def _detect_nginx_paths() -> tuple[str, str]:
    """Detect nginx binary and config directory, platform-aware."""
    candidates_bin = [
        "/usr/sbin/nginx",
        "/usr/local/bin/nginx",
        "/opt/homebrew/bin/nginx",
    ]
    nginx_bin = next((p for p in candidates_bin if os.path.isfile(p)), "/usr/sbin/nginx")

    if sys.platform == "darwin":
        if os.uname().machine == "arm64":
            conf_dir = "/opt/homebrew/etc/nginx"
        else:
            conf_dir = "/usr/local/etc/nginx"
    else:
        conf_dir = "/etc/nginx"

    return nginx_bin, conf_dir

NGINX_BIN, NGINX_CONF_DIR = _detect_nginx_paths()
BLOCKED_CONF = os.path.join(NGINX_CONF_DIR, "blocked_ips.conf")
ALLOW_MANUAL_CONF = os.path.join(NGINX_CONF_DIR, "allow-ips-manual.conf")


def _fix_orphaned_nginx() -> str | None:
    """Detect and kill orphaned nginx master running outside systemd.

    When nginx is started manually (not via systemd), systemd loses track
    of the process. The old master holds ports and blocks systemd from
    starting. This function kills the orphan and returns a message.
    Returns None if no orphan found.
    """
    # Check systemd status
    r = subprocess.run(
        ["systemctl", "is-active", "nginx"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0 and r.stdout.strip() == "active":
        return None  # systemd is managing it

    # Check process table for nginx master
    r2 = subprocess.run(
        ["pgrep", "-f", "nginx: master"],
        capture_output=True, text=True, timeout=10,
    )
    if not r2.stdout.strip():
        return None  # no master process at all

    orphan_pids = []
    for pid_str in r2.stdout.strip().split():
        pid = int(pid_str)

        # Check if this specific PID is tracked by systemd
        r3 = subprocess.run(
            ["systemctl", "show", "-p", "MainPID", "nginx"],
            capture_output=True, text=True, timeout=10,
        )
        main_pid = r3.stdout.strip().split("=")[-1] if "=" in r3.stdout.strip() else "0"
        if pid_str == main_pid:
            continue  # this IS the systemd-managed PID

        orphan_pids.append(pid)

    if not orphan_pids:
        return None

    killed = []
    for pid in orphan_pids:
        os.kill(pid, signal.SIGTERM)
        for _ in range(5):
            try:
                os.kill(pid, 0)  # still alive?
                time.sleep(1)
            except OSError:
                break
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
            killed.append(f"{pid}(SIGKILL)")
        except OSError:
            killed.append(f"{pid}(TERM)")

    # Write correct PID file so systemd can track
    pid_file = "/run/nginx.pid"
    if orphan_pids and os.path.exists(pid_file):
        try:
            with open(pid_file, "w") as f:
                f.write(str(orphan_pids[0]))
        except OSError as e:
            return f"orphan(s) killed ({', '.join(killed)}) but PID file write failed: {e}"

    return f"orphan nginx master(s) killed: {', '.join(killed)}"


def is_valid_public_ip(s: str) -> bool:
    """Return True if s is a valid public IPv4 address (not private/reserved). Accepts CIDR notation."""
    m = CIDR_PREFIX_RE.match(s)
    ip_part = m.group(1) if m else s
    if not IPV4_RE.match(s):
        return False
    parts = [int(p) for p in ip_part.split(".")]
    if not all(0 <= p <= 255 for p in parts):
        return False
    if PRIVATE_RANGES.match(ip_part):
        return False
    return True


def repo_dir() -> str:
    """Detect the hermes-cortex repo directory by walking up from script location."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Walk up from script location until we find .git or hit root
    current = script_dir
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break  # hit filesystem root
        current = parent
    # Fallback: try ~/hermes-cortex
    home = os.environ.get("HOME") or os.path.expanduser("~")
    candidate2 = os.path.join(home, "hermes-cortex")
    if os.path.isdir(candidate2):
        return candidate2
    return script_dir


def read_allow_lines() -> list[str]:
    """Preserve existing allow rules from the current blocked_ips.conf."""
    allow_lines = []
    if os.path.exists(BLOCKED_CONF):
        with open(BLOCKED_CONF) as f:
            for line in f:
                if line.startswith("allow "):
                    allow_lines.append(line.rstrip())
    return allow_lines


def read_manual_allowed() -> set[str]:
    """Read IPs from allow-ips-manual.conf that must never be in the blocklist."""
    manual = set()
    if os.path.exists(ALLOW_MANUAL_CONF):
        with open(ALLOW_MANUAL_CONF) as f:
            for line in f:
                line = line.strip()
                if line.startswith("allow ") and line.endswith(";"):
                    ip = line[6:].rstrip(";").strip()
                    if IPV4_RE.match(ip):
                        manual.add(ip)
        if manual:
            print(f"  📋 {len(manual)} IPs in manual allow list — excluded from blocklist")
    return manual


def generate_config() -> tuple[list[str], str]:
    """Read blocked_ips.add, validate IPs, return (lines, summary_message)."""
    rdir = repo_dir()
    source = os.path.join(rdir, "ops", "install", "deploy", "nginx", "blocked_ips.add")

    if not os.path.exists(source):
        print(f"✗ Source not found: {source}")
        sys.exit(1)

    allow_lines = read_allow_lines()
    manual_allowed = read_manual_allowed()

    ips: list[str] = []
    skipped: list[str] = []
    with open(source) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if is_valid_public_ip(line):
                if line not in manual_allowed:
                    ips.append(line)
                else:
                    skipped.append(f"{line} (allow-listed)")
            else:
                skipped.append(line)

    if skipped:
        print(f"  ⚠ Skipped {len(skipped)} invalid entries")
        for s in skipped[:3]:
            print(f"     invalid: {s}")

    lines = list(allow_lines)
    lines.append("")
    for ip in ips:
        lines.append(f"deny {ip};")

    summary = f"  ✓ Generated: {len(ips)} blocked IPs (+ {len(allow_lines)} allow rules)"
    return lines, summary


def deploy_via_sudo(config_lines: list[str]) -> None:
    """Write config, atomic rename, validate, reload — all as root."""
    new_conf = BLOCKED_CONF + ".new"
    content = "\n".join(config_lines) + "\n"
    with open(new_conf, "w") as f:
        f.write(content)
    os.chmod(new_conf, 0o644)

    # Atomic rename on same filesystem
    os.rename(new_conf, BLOCKED_CONF)
    print(f"  ✓ Installed {BLOCKED_CONF}")

    # Validate nginx config
    result = subprocess.run(
        [NGINX_BIN, "-t"], capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        print(f"  ✗ nginx config INVALID:")
        for line in result.stderr.strip().split("\n"):
            print(f"     {line}")
        sys.exit(1)
    print(f"  ✓ nginx config valid")

    # Reload nginx
    result = subprocess.run(
        [NGINX_BIN, "-s", "reload"], capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        print(f"  ✗ nginx reload FAILED:")
        for line in result.stderr.strip().split("\n"):
            print(f"     {line}")
        sys.exit(1)
    print(f"  ✓ nginx reloaded")


def deploy_via_temp(config_lines: list[str]) -> str:
    """Fallback: write to /tmp/ for non-root mode (legacy)."""
    tmp_path = "/tmp/blocked_ips.conf.new"
    content = "\n".join(config_lines) + "\n"
    with open(tmp_path, "w") as f:
        f.write(content)
    return tmp_path


def main():
    # Fix orphaned nginx before anything else — ensures systemd can manage it
    orphan_msg = _fix_orphaned_nginx()
    if orphan_msg:
        print(f"  🔧 nginx: {orphan_msg}")

    is_root = os.geteuid() == 0
    if not is_root:
        print("⚠ Non-root mode — generating config to /tmp/ only")
        print("  Run with: sudo fix-blocked-ips.py for full deploy")
        print()

    lines, summary = generate_config()
    print(summary)

    ip_count = sum(1 for l in lines if l.startswith("deny "))
    allow_count = sum(1 for l in lines if l.startswith("allow "))

    if ip_count == 0 and allow_count == 0:
        print("  ℹ No IPs or allow rules — skipping")
        return

    if is_root:
        deploy_via_sudo(lines)
    else:
        tmp_path = deploy_via_temp(lines)
        print(f"  → {tmp_path}")
        print(f"  → Install: sudo cp {tmp_path} {BLOCKED_CONF} && sudo {NGINX_BIN} -t && sudo {NGINX_BIN} -s reload")


if __name__ == "__main__":
    main()
