#!/usr/bin/env python3
"""
koscap-workday-watchdog.py — KOSCAP production health watchdog.

no_agent cron: runs Mon-Fri 9am-5pm every hour.
Silent when healthy, noisy on failure (watchdog pattern).

Checks:
  1. Docker container health (18 containers)
  2. Disk usage
  3. Memory pressure
  4. Nginx process health
  5. SSL certificate expiry (Let's Encrypt)
  6. MWEB HTTP health
  7. MWI Tomcat health
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

# ── Configuration ─────────────────────────────────────────────
COMPOSE_DIR = Path("/home/app/mwi/koscap-mwi")
BACKUPS_DB = Path("/home/app/mwi/backups_db")
BACKUPS_VOLUME = Path("/home/app/mwi/backups_docker_volume")
BACKUPS_MWI = Path("/home/app/mwi/backups_mwi")
SSL_CERT = Path("/etc/letsencrypt/live/mp.koscap.or.kr/fullchain.pem")

DISK_THRESHOLD_PCT = 80
MEM_AVAIL_THRESHOLD_GB = 40
SWAP_THRESHOLD_MB = 100
SSL_DAYS_THRESHOLD = 30
BACKUP_MAX_AGE_HOURS = 28  # allow ~4h grace past expected 23:00 run


def run(cmd, timeout=15):
    """Run a shell command, return (stdout, stderr, exit_code)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except FileNotFoundError:
        return "", f"command not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", -1


def check_docker_containers():
    """Check all 18 containers are up, web/tomcat/postgres are healthy."""
    issues = []
    stdout, _, _ = run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"])
    lines = [l for l in stdout.split("\n") if l.strip()]
    names_seen = set()

    for line in lines:
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        name, status = parts
        names_seen.add(name)
        if "unhealthy" in status.lower():
            issues.append(f"⚠️  {name} — UNHEALTHY: {status}")
        elif "restarting" in status.lower():
            issues.append(f"⚠️  {name} — RESTARTING: {status}")
        elif "exited" in status.lower():
            issues.append(f"⚠️  {name} — EXITED: {status}")

    # Known expected containers (MWI + MWEB + Langfuse)
    expected_containers = {
        "mwi-tomcat-1", "mwi-postgres02-1",
        "mweb-web-1", "mweb-worker-1", "mweb-cable-1", "mweb-redis-1",
        "mweb-postgres01-1", "mweb-imports_db01-1", "mweb-chrome-1",
        "mweb-analytics_db01-1", "mweb-cloudbeaver-1", "mweb-audits_db01-1",
        "langfuse-langfuse-web-1", "langfuse-langfuse-worker-1",
        "langfuse-clickhouse-1", "langfuse-postgres-1",
        "langfuse-redis-1", "langfuse-minio-1",
    }
    missing = expected_containers - names_seen
    for m in sorted(missing):
        issues.append(f"❌ {m} — NOT RUNNING")

    # Also check restart counts
    stdout2, _, _ = run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.RestartCount}}"]
    )
    for line in stdout2.strip().split("\n"):
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[1].strip() != "0":
            issues.append(f"⚠️  {parts[0]} — {parts[1]} restart(s)")

    return issues


def check_disk():
    """Check disk usage percentage."""
    issues = []
    stdout, _, _ = run(["df", "-h", "/"])
    lines = stdout.split("\n")
    for line in lines:
        parts = line.split()
        if len(parts) >= 5 and parts[0].startswith("/"):
            pct_str = parts[4].rstrip("%")
            try:
                pct = int(pct_str)
                if pct >= DISK_THRESHOLD_PCT:
                    issues.append(f"⚠️  DISK at {pct}% (threshold: {DISK_THRESHOLD_PCT}%) — {parts[2]} used / {parts[1]} total")
            except ValueError:
                pass
    return issues


def check_memory():
    """Check available memory and swap."""
    issues = []
    stdout, _, _ = run(["free", "-h"])
    lines = stdout.split("\n")
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "Mem:" and len(parts) >= 7:
            avail_str = parts[6]
            swap_str = ""
        elif parts[0] == "Swap:" and len(parts) >= 3:
            swap_str = parts[2]

    # Parse available memory
    stdout2, _, _ = run(["free", "--bytes"])
    for line in stdout2.split("\n"):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "Mem:" and len(parts) >= 7:
            try:
                avail_bytes = int(parts[6])
                avail_gb = avail_bytes / (1024**3)
                if avail_gb < MEM_AVAIL_THRESHOLD_GB:
                    issues.append(f"⚠️  LOW MEMORY: {avail_gb:.1f} GB available (threshold: {MEM_AVAIL_THRESHOLD_GB} GB)")
            except ValueError:
                pass
        if parts[0] == "Swap:" and len(parts) >= 3:
            try:
                swap_bytes = int(parts[2])
                swap_mb = swap_bytes / (1024**2)
                if swap_mb > SWAP_THRESHOLD_MB:
                    issues.append(f"⚠️  HIGH SWAP: {swap_mb:.1f} MB used (threshold: {SWAP_THRESHOLD_MB} MB)")
            except ValueError:
                pass
    return issues


def check_nginx():
    """Check nginx master process is running."""
    issues = []
    stdout, _, _ = run(["pgrep", "-f", "nginx: master"])
    if not stdout.strip():
        issues.append("❌ NGINX — master process not running")
    return issues


def check_ssl():
    """Check Let's Encrypt SSL cert expiry."""
    issues = []
    if not SSL_CERT.exists():
        issues.append(f"❌ SSL — cert not found at {SSL_CERT}")
        return issues

    stdout, _, _ = run([
        "openssl", "x509", "-enddate", "-noout",
        "-in", str(SSL_CERT),
    ])
    if "notAfter=" not in stdout:
        issues.append(f"⚠️  SSL — could not parse cert expiry from {SSL_CERT}")
        return issues

    date_str = stdout.split("notAfter=", 1)[1].strip()
    try:
        expiry = datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_left = (expiry - now).days
        if days_left < SSL_DAYS_THRESHOLD:
            issues.append(f"⚠️  SSL — expires in {days_left} day(s) (threshold: {SSL_DAYS_THRESHOLD})")
    except ValueError:
        issues.append(f"⚠️  SSL — could not parse date: {date_str}")
    return issues


def check_mweb_health():
    """Check MWEB web responds on :3000."""
    issues = []
    stdout, _, rc = run(["curl", "-sSf", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:3000/"])
    if rc != 0 or stdout != "200":
        issues.append(f"❌ MWEB (:3000) — HTTP {stdout or 'timeout'}")
    return issues


def check_mwi_health():
    """Check MWI Tomcat health via nginx proxy."""
    issues = []
    stdout, _, rc = run(["curl", "-sSf", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8888/"])
    if rc != 0 or stdout not in ("200", "302"):
        issues.append(f"❌ MWI (:8888) — HTTP {stdout or 'timeout'}")
    return issues


def check_backup_freshness():
    """Check backup directories for recent files."""
    issues = []
    now = datetime.now()
    checks = [
        ("DB", BACKUPS_DB, "*.tar.gz"),
        ("Volume", BACKUPS_VOLUME, "*.tar.gz"),
        ("App (MWI)", BACKUPS_MWI, "*.zip"),
    ]
    for label, directory, pattern in checks:
        if not directory.exists():
            issues.append(f"⚠️  BACKUP {label} — directory missing: {directory}")
            continue
        stdout, _, _ = run(["find", str(directory), "-maxdepth", "1", "-name", pattern, "-type", "f", "-mmin", f"-{BACKUP_MAX_AGE_HOURS * 60}", "-print", "-quit"])
        if not stdout.strip():
            # Check if any file exists at all
            stdout2, _, _ = run(["ls", "-lt", str(directory)])
            newest = stdout2.split("\n")[0] if stdout2.strip() else "(empty)"
            issues.append(f"⚠️  BACKUP {label} — no recent file in <{BACKUP_MAX_AGE_HOURS}h ({newest})")
    return issues


def main():
    now = datetime.now(KST)
    issues = []

    # Run all checks
    issues.extend(check_docker_containers())
    issues.extend(check_disk())
    issues.extend(check_memory())
    issues.extend(check_nginx())
    issues.extend(check_ssl())
    issues.extend(check_mweb_health())
    issues.extend(check_mwi_health())
    issues.extend(check_backup_freshness())

    if not issues:
        # Silent — watchdog pattern
        sys.exit(0)

    # Report issues
    print(f"🔴 KOSCAP Workday Watchdog — {now.strftime('%Y-%m-%d %H:%M KST')}")
    print(f"{'─' * 50}")
    for issue in issues:
        print(f"  {issue}")
    print(f"{'─' * 50}")
    print(f"Total: {len(issues)} issue(s)")
    sys.exit(1)


if __name__ == "__main__":
    main()
