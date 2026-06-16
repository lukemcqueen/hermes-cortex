#!/usr/bin/env python3
"""remediation-sensor.py — Companion script for cron-auto-remediate.

Runs every 5m as a no_agent watchdog. Gathers diagnostics and outputs
structured JSON if issues are found. Silent when healthy.

Output: JSON array of issue objects on stdout. Empty array = nothing to do.

Output shape:
[
  {
    "type": "script_missing|git_issue|perm_issue|disk_low|mem_pressure|service_down|nginx_issue|web_cache_large|inbox_marker",
    "severity": "critical|high|medium|low",
    "detail": "human-readable description",
    "context": {},
    "timestamp": "2026-06-15T18:30:00Z"
  }
]

Called from cron-auto-remediate (no_agent cron, every 5m).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HERMES_SCRIPTS = HOME / ".hermes" / "scripts"
STATE_DIR = HOME / ".hermes" / "state"
CORTEX_REPO = HOME / "hermes-cortex"
CORTEX_SCRIPTS = CORTEX_REPO / "src" / "scripts"
WEB_CACHE = HOME / ".hermes" / "data" / "web_cache.sqlite"

ISSUES = []


def add_issue(typ, severity, detail, context=None):
    """Add an issue to the report."""
    ISSUES.append({
        "type": typ,
        "severity": severity,
        "detail": detail,
        "context": context or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def run(cmd, timeout=15):
    """Run a shell command, return (stdout, stderr, rc)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            shell=True, executable="/bin/bash",
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def check_scripts():
    """Check for missing or non-executable scripts."""
    required_scripts = [
        "heartbeat.py", "service-recovery.py", "system-alert.py",
        "check-agent-messages.sh", "cron-auto-remediate.sh",
        "daily-lesson-mine.sh", "update-session-state.sh",
    ]
    for script in required_scripts:
        path = HERMES_SCRIPTS / script
        if not path.exists():
            add_issue("script_missing", "high", f"Missing script: {script}", {"path": str(path)})
        elif not os.access(str(path), os.X_OK):
            add_issue("perm_issue", "low", f"Non-executable: {script}", {"path": str(path)})


def check_git():
    """Check git health of cortex repo."""
    if not CORTEX_REPO.exists():
        return
    # Detached HEAD
    out, _, rc = run(f"cd {CORTEX_REPO} && git symbolic-ref -q HEAD 2>/dev/null")
    if rc != 0:
        add_issue("git_issue", "medium", "Detached HEAD in cortex repo", {"repo": str(CORTEX_REPO)})
    # Merge conflicts
    out, _, _ = run(f"cd {CORTEX_REPO} && git status --porcelain 2>/dev/null | grep -c '^UU'")
    if out.strip() and int(out.strip()) > 0:
        add_issue("git_issue", "critical", "Merge conflicts in cortex repo", {"repo": str(CORTEX_REPO)})
    # Dirty scripts
    out, _, _ = run(f"cd {CORTEX_REPO} && git status --porcelain -- src/scripts/ 2>/dev/null | head -3")
    if out.strip():
        add_issue("git_issue", "low", "Uncommitted changes in src/scripts/", {"repo": str(CORTEX_REPO)})


def check_disk():
    """Check disk usage."""
    out, _, rc = run("df -h / 2>/dev/null | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'")
    if rc == 0 and out.strip():
        pct = int(out.strip())
        if pct > 90:
            add_issue("disk_low", "critical", f"Disk at {pct}%", {"pct": pct})
        elif pct > 85:
            add_issue("disk_low", "high", f"Disk at {pct}%", {"pct": pct})
        elif pct > 75:
            add_issue("disk_low", "medium", f"Disk at {pct}%", {"pct": pct})


def check_memory():
    """Check memory pressure (macOS)."""
    out, _, rc = run("memory_pressure 2>/dev/null | grep 'System-wide memory' | sed 's/.* \\([0-9]*\\)%/\\1/'")
    if rc == 0 and out.strip():
        free_pct = int(out.strip())
        if free_pct < 10:
            add_issue("mem_pressure", "critical", f"Memory pressure high: {free_pct}% free", {"free_pct": free_pct})
        elif free_pct < 15:
            add_issue("mem_pressure", "high", f"Memory pressure elevated: {free_pct}% free", {"free_pct": free_pct})


def check_services():
    """Check critical services (macOS launchd)."""
    services = {
        "com.ollama.serve": "Ollama",
        "com.gbrain.autopilot": "gbrain autopilot",
        "com.gbrain.sync-watch": "gbrain sync-watch",
    }
    for label, name in services.items():
        out, _, rc = run(f"launchctl list {label} 2>/dev/null | awk 'NR==2 {{print $1}}'")
        if rc != 0 or not out.strip() or out.strip() == "-":
            add_issue("service_down", "high", f"{name} is down", {"service": label})


def check_nginx():
    """Check nginx config and process."""
    out, _, rc = run("nginx -t 2>&1")
    if rc != 0:
        add_issue("nginx_issue", "critical", "Nginx config invalid", {"error": out})
    out, _, rc = run("pgrep -f 'nginx: master' 2>/dev/null")
    if rc != 0:
        add_issue("nginx_issue", "high", "Nginx not running", {})


def check_web_cache():
    """Check web cache size."""
    if WEB_CACHE.exists():
        size_mb, _, rc = run(f"du -m {WEB_CACHE} 2>/dev/null | cut -f1")
        if rc == 0 and size_mb.strip():
            mb = int(size_mb.strip())
            if mb > 200:
                add_issue("web_cache_large", "medium", f"Web cache at {mb}MB", {"size_mb": mb})


def check_inbox_markers():
    """Check for pending remediation markers."""
    remediate_dir = STATE_DIR / "remediate"
    if remediate_dir.exists():
        markers = list(remediate_dir.glob("inbox-*.txt"))
        # Exclude done/ subdir
        markers = [m for m in markers if m.parent.name == "remediate" and "done" not in str(m.parent)]
        if markers:
            for m in markers[:5]:  # Report up to 5
                content = m.read_text().strip()
                add_issue("inbox_marker", "medium", f"Pending remediation: {m.name}", {"file": str(m), "content": content})
            if len(markers) > 5:
                add_issue("inbox_marker", "low", f"... and {len(markers) - 5} more pending markers", {})


def check_certs():
    """Check SSL certificate expiry for all nginx-referenced certs.
    Silent (no issues) when all certs exist and are >30 days from expiry.
    """
    now = datetime.now(timezone.utc)

    # Auto-discover nginx SSL cert paths from config files
    cert_files = set()
    for d in ["/usr/local/etc/nginx/servers", "/usr/local/etc/nginx",
              "/opt/homebrew/etc/nginx/servers", "/opt/homebrew/etc/nginx",
              "/etc/nginx/sites-enabled", "/etc/nginx/conf.d"]:
        conf_dir = Path(d)
        if conf_dir.exists():
            for conf_file in conf_dir.glob("*.conf"):
                try:
                    content = conf_file.read_text()
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue
                        for m in __import__("re").finditer(r'ssl_certificate\s+(\S+);', stripped):
                            path = m.group(1).strip().rstrip(";")
                            if path:
                                cert_files.add(path)
                except (OSError, IOError):
                    pass

    if not cert_files:
        # No ssl_certificate found — nginx may be local-only, no certs needed
        return

    for cert_path in sorted(cert_files):
        p = Path(cert_path)
        domain = p.parent.name if p.parent else "unknown"

        if not p.exists():
            add_issue("cert_missing", "critical",
                      f"SSL cert missing: {cert_path}",
                      {"path": cert_path, "domain": domain})
            continue

        # Read certificate expiry date
        out, _, rc = run(
            f"openssl x509 -in '{cert_path}' -noout -enddate 2>/dev/null | cut -d= -f2"
        )
        if rc != 0 or not out.strip():
            add_issue("cert_unreadable", "high",
                      f"Cannot read cert expiry: {cert_path}",
                      {"path": cert_path, "domain": domain})
            continue

        try:
            expiry_str = out.strip()
            # Strip trailing timezone name (e.g. " GMT") and parse as UTC
            for known_tz in [" GMT", " UTC", " EST", " EDT", " PST", " PDT"]:
                if expiry_str.endswith(known_tz):
                    expiry_str = expiry_str[:-len(known_tz)]
                    break
            expiry = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y")
            # Assume UTC for cert dates (Let's Encrypt uses UTC)
            expiry = expiry.replace(tzinfo=timezone.utc)
            days_left = (expiry - now).days

            if days_left < 0:
                add_issue("cert_expired", "critical",
                          f"SSL cert expired {abs(days_left)}d ago: {domain}",
                          {"path": cert_path, "domain": domain, "days_expired": abs(days_left)})
            elif days_left < 7:
                add_issue("cert_expiring_soon", "critical",
                          f"SSL cert expires in {days_left}d: {domain}",
                          {"path": cert_path, "domain": domain, "days_left": days_left})
            elif days_left < 30:
                add_issue("cert_expiring_soon", "high",
                          f"SSL cert expires in {days_left}d: {domain}",
                          {"path": cert_path, "domain": domain, "days_left": days_left})
            # else: >30 days — silent, no issue
        except ValueError as e:
            add_issue("cert_unreadable", "low",
                      f"Cannot parse cert date '{out.strip()}': {e}",
                      {"path": cert_path, "domain": domain})


def check_errored_crons():
    """Check for errored cron jobs by reading jobs.json directly."""
    jobs_json = HOME / ".hermes" / "cron" / "jobs.json"
    if jobs_json.exists():
        try:
            data = json.loads(jobs_json.read_text())
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            for job in jobs:
                status = job.get("last_status", "")
                if status == "error":
                    add_issue("cron_error", "high", f"Errored cron: {job.get('name', job.get('job_id', 'unknown'))}", {
                        "job_id": job.get("job_id"),
                        "name": job.get("name"),
                        "last_status": status,
                    })
        except (json.JSONDecodeError, KeyError):
            pass


def main():
    # Run all checks
    check_scripts()
    check_git()
    check_disk()
    check_memory()
    check_services()
    check_nginx()
    check_web_cache()
    check_inbox_markers()
    check_certs()
    check_errored_crons()

    # Output JSON
    print(json.dumps(ISSUES, indent=2))


if __name__ == "__main__":
    main()
