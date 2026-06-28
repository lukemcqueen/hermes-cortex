#!/usr/bin/env python3
"""remediation-sensor.py — Companion script for agent-auto-remediate.

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

Called from agent-auto-remediate (LLM-driven cron, every 5m).
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
CORTEX_REPO_ENV = os.environ.get("CORTEX_REPO", "")
if CORTEX_REPO_ENV:
    CORTEX_REPO = Path(CORTEX_REPO_ENV)
else:
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
        "service-recovery.py", "system-alert.py",
        "orch-team-messages.sh", "cron-auto-remediate.sh",
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
    """Check memory pressure (macOS + Linux)."""
    if sys.platform == "darwin":
        out, _, rc = run("memory_pressure 2>/dev/null | grep 'System-wide memory' | sed 's/.* \\([0-9]*\\)%/\\1/'")
        if rc == 0 and out.strip():
            free_pct = int(out.strip())
            if free_pct < 10:
                add_issue("mem_pressure", "critical", f"Memory pressure high: {free_pct}% free", {"free_pct": free_pct})
            elif free_pct < 15:
                add_issue("mem_pressure", "high", f"Memory pressure elevated: {free_pct}% free", {"free_pct": free_pct})
    elif sys.platform.startswith("linux"):
        out, _, rc = run(r"free -m | awk '/Mem:/ {printf \"%.0f\", $3/$2 * 100}'")
        if rc == 0 and out.strip():
            used_pct = int(out.strip())
            free_pct = 100 - used_pct
            if free_pct < 10:
                add_issue("mem_pressure", "critical", f"Memory at {used_pct}% used ({free_pct}% free)", {"used_pct": used_pct})
            elif free_pct < 15:
                add_issue("mem_pressure", "high", f"Memory at {used_pct}% used ({free_pct}% free)", {"used_pct": used_pct})


def check_services():
    """Check critical services (macOS launchd / Linux systemd)."""
    if sys.platform == "darwin":
        # Ollama is always required
        out, _, rc = run("launchctl list com.ollama.serve 2>/dev/null | awk 'NR==2 {print $1}'")
        if rc != 0 or not out.strip() or out.strip() == "-":
            add_issue("service_down", "high", "Ollama is down", {"service": "com.ollama.serve"})
        # Gbrain: at least ONE of autopilot or sync-watch must be running
        autopilot_ok = False
        sync_watch_ok = False
        out, _, rc = run("launchctl list com.gbrain.autopilot 2>/dev/null | awk 'NR==2 {print $1}'")
        if rc == 0 and out.strip() and out.strip() != "-":
            autopilot_ok = True
        out, _, rc = run("launchctl list com.gbrain.sync-watch 2>/dev/null | awk 'NR==2 {print $1}'")
        if rc == 0 and out.strip() and out.strip() != "-":
            sync_watch_ok = True
        if not autopilot_ok and not sync_watch_ok:
            add_issue("service_down", "high", "No gbrain sync service running (autopilot or sync-watch)", {"services": ["com.gbrain.autopilot", "com.gbrain.sync-watch"]})
    elif sys.platform.startswith("linux"):
        # Ollama user service — check systemd first, then process fallback
        out, _, rc = run("systemctl --user is-active ollama 2>/dev/null")
        if out.strip() != "active":
            # systemd may report inactive when Ollama runs as standalone daemon
            # (no systemd unit). Fall back to process check.
            proc_out, _, proc_rc = run("pgrep -f 'ollama serve' 2>/dev/null")
            if proc_rc != 0 or not proc_out.strip():
                add_issue("service_down", "high", f"Ollama is not active (systemd user service)", {"service": "ollama.service", "status": out.strip() or "unknown", "note": "process check also failed"})
        # Gbrain sync-watch user service
        out, _, rc = run("systemctl --user is-active com.gbrain.sync-watch 2>/dev/null")
        if rc == 0 and out.strip() != "active":
            add_issue("service_down", "high", f"gbrain sync-watch is not active (systemd user service)", {"service": "com.gbrain.sync-watch.service", "status": out.strip() or "unknown"})


def check_nginx():
    """Check nginx config and process.
    
    Uses sudo -n for non-interactive sudo (works if user has NOPASSWD for nginx).
    Falls back to direct check if sudo unavailable.
    Skips gracefully if no root/sudo access and nginx -t fails.
    """
    # Try sudo -n first (non-interactive, fails fast if no sudo)
    out, _, rc = run("sudo -n nginx -t 2>&1")
    if rc != 0:
        # Try without sudo (might work if user has direct access)
        out2, _, rc2 = run("nginx -t 2>&1")
        if rc2 != 0:
            # Both failed — only report if it looks like a real config error
            # (not a permission error)
            if "permission" not in out2.lower() and "permission" not in out.lower():
                add_issue("nginx_issue", "critical", "Nginx config invalid", {"error": out2})
    # Check process
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


def check_gbrain_health():
    """Check gbrain/PGLite health.
    
    Detects PGLite WASM runtime failures (common on Linux with glibc/kernel incompat).
    Runs gbrain sync --no-pull and checks for WASM abort errors.
    """
    # Check if gbrain is installed
    if not os.path.exists(os.path.expanduser("~/.gbrain")):
        return  # gbrain not installed, skip
    
    # Run gbrain sync and capture output
    out, err, rc = run("gbrain sync --all --no-pull 2>&1", timeout=60)
    combined = (out + " " + err).lower()
    
    # Check for PGLite WASM failure patterns
    if "pglite failed to initialize its wasm runtime" in combined:
        add_issue("gbrain_wasm_failure", "critical", "gbrain PGLite WASM runtime failed to initialize", {
            "error_snippet": (out + err)[:500],
            "upstream_issue": "https://github.com/garrytan/gbrain/issues/223",
        })
    elif "aborted()" in combined and "wasm" in combined:
        add_issue("gbrain_wasm_failure", "critical", "gbrain PGLite WASM aborted", {
            "error_snippet": (out + err)[:500],
        })
    elif rc != 0 and "could not connect" in combined:
        add_issue("gbrain_connection_failure", "high", "gbrain cannot connect to configured database", {
            "error_snippet": (out + err)[:300],
        })


def check_ssl_certs():
    """Check SSL certificate renewal capability.
    
    SUDOERS ASSUMED: gisu/kustos/joseph have NOPASSWD sudoers for certbot.
    Verifies sudo -n certbot commands work correctly.
    
    NOTE: /etc/letsencrypt/{live,archive} being 700 root:root is CORRECT
    and SECURE. Certbot should run via sudo, not direct access.
    """
    # Check common nginx SSL cert locations
    cert_dirs = [
        "/etc/letsencrypt/live",
        "/etc/ssl/certs",
        "/usr/local/etc/nginx/servers",
    ]
    
    # Check if certbot systemd timer is active (preferred method)
    timer_active = False
    if os.path.exists("/usr/bin/systemctl"):
        out, _, rc = run("systemctl is-active certbot.timer 2>/dev/null")
        if out.strip() == "active":
            timer_active = True
    
    # Check if user has sudoers entry for certbot (PRIMARY METHOD for cisnet02)
    # Test the actual commands in sudoers: certbot certificates and certbot renew
    has_sudoers = False
    sudoers_test_failed = False
    try:
        # Test certbot certificates (read-only, safe to test)
        out, _, rc = run("sudo -n certbot certificates 2>&1 | head -3")
        if rc == 0 or "Certificate Name" in out or "Found" in out:
            has_sudoers = True
        else:
            # Try certbot renew --dry-run as fallback test
            out2, _, rc2 = run("sudo -n certbot renew --dry-run 2>&1 | head -5")
            if rc2 == 0 or "dry run" in out2.lower():
                has_sudoers = True
            else:
                sudoers_test_failed = True
    except:
        sudoers_test_failed = True
    
    # If either method is available, certs are properly configured
    if timer_active or has_sudoers:
        return  # Certbot can renew securely
    
    # If we get here, certbot renewal may fail
    # Report as informational — user should configure sudoers or enable timer
    for cert_dir in cert_dirs:
        if os.path.exists(cert_dir):
            issue_data = {
                "directory": cert_dir,
                "note": "700 root:root permissions are CORRECT and SECURE",
                "fix_hint": "Add to sudoers: sudo visudo, then add: " + os.environ.get("USER", "user") + " ALL=(ALL) NOPASSWD: /usr/bin/certbot certificates, /usr/bin/certbot renew --non-interactive",
                "alternative": "Enable systemd timer: sudo systemctl enable certbot.timer && sudo systemctl start certbot.timer",
            }
            if sudoers_test_failed:
                issue_data["debug"] = "sudo -n certbot test failed — check sudoers configuration"
            add_issue("ssl_cert_sudoers_missing", "medium", 
                "Certbot renewal not configured for non-root execution",
                issue_data)
            break


def check_certbot():
    """Check certbot execution capability.
    
    SUDOERS ASSUMED: gisu/kustos/joseph have NOPASSWD sudoers for certbot.
    Verifies sudo -n certbot certificates and sudo -n certbot renew work.
    
    NOTE: Lock file being root-owned is CORRECT and SECURE.
    """
    lock_file = "/var/log/letsencrypt/.certbot.lock"
    log_dir = "/var/log/letsencrypt"
    
    # Check if certbot systemd timer is active
    timer_active = False
    if os.path.exists("/usr/bin/systemctl"):
        out, _, rc = run("systemctl is-active certbot.timer 2>/dev/null")
        if out.strip() == "active":
            timer_active = True
    
    # Check if user has sudoers entry for certbot (PRIMARY METHOD for cisnet02)
    # Test the actual commands: certbot certificates and certbot renew
    has_sudoers = False
    try:
        # Test certbot certificates (read-only, safe to test)
        out, _, rc = run("sudo -n certbot certificates 2>&1 | head -5")
        if rc == 0 or "Certificate Name" in out or "Found" in out or "No certs" in out:
            has_sudoers = True
        else:
            # Try certbot renew --dry-run as fallback test
            out2, _, rc2 = run("sudo -n certbot renew --dry-run 2>&1 | head -5")
            if rc2 == 0 or "dry run" in out2.lower():
                has_sudoers = True
    except:
        pass
    
    # If either method works, certbot is properly configured
    if timer_active or has_sudoers:
        return  # Certbot can run securely
    
    # Check if lock file exists and is owned by root (correct)
    if os.path.exists(lock_file):
        owner = run("stat -c '%U' " + lock_file + " 2>/dev/null")[0].strip()
        if owner == "root":
            # Lock file permissions are correct — just need sudoers config
            add_issue("certbot_sudoers_missing", "medium",
                "Certbot lock file is secure but no renewal method configured",
                {
                    "lock_file": lock_file,
                    "owner": owner,
                    "note": "Root ownership is CORRECT and SECURE",
                    "fix_hint": "Add to sudoers: sudo visudo, then add: " + os.environ.get("USER", "user") + " ALL=(ALL) NOPASSWD: /usr/bin/certbot certificates, /usr/bin/certbot renew --non-interactive",
                    "alternative": "Use systemd timer: sudo systemctl enable certbot.timer",
                })


def check_systemd_services():
    """Check critical systemd services (Linux only).
    
    Complements macOS launchd checks for cross-platform support.
    """
    if sys.platform == "darwin":
        return  # Skip on macOS
    
    # Check for systemctl availability
    if not os.path.exists("/usr/bin/systemctl") and not os.path.exists("/bin/systemctl"):
        return  # systemd not available
    
    # Known benign masked/failed services (e.g., from Ubuntu packages like casper)
    # These are benign for this stack and should never be reported as issues
    BENIGN_MASKED_SERVICES = {
        "casper-md5check.service",  # Ubuntu live ISO checksum verify - masked by default
        "vsftpd.service",           # FTP server not used on this stack
    }
    
    services = {
        "nginx.service": "nginx",
        "docker.service": "Docker",
        "fail2ban.service": "fail2ban",
    }
    
    for svc, name in services.items():
        out, _, rc = run(f"systemctl is-active {svc} 2>/dev/null")
        if out.strip() != "active":
            # For nginx, also check if it's running as a master process outside systemd
            if svc == "nginx.service":
                pg_out, _, pg_rc = run("pgrep -f 'nginx: master' 2>/dev/null")
                if pg_rc == 0 and pg_out.strip():
                    # nginx is running as a process, not managed by systemd
                    continue
            # Skip benign masked/failed services
            if svc in BENIGN_MASKED_SERVICES:
                continue
            add_issue("service_down", "high", f"{name} is not active (systemd)", {
                "service": svc,
                "status": out.strip() or "unknown",
            })


def main():
    # Run all checks
    check_scripts()
    check_git()
    check_disk()
    check_memory()
    check_services()
    check_systemd_services()  # Linux complement to check_services()
    check_nginx()
    check_ssl_certs()  # NEW: SSL cert permissions
    check_certbot()  # NEW: certbot execution capability
    check_gbrain_health()  # NEW: gbrain/PGLite WASM health
    check_web_cache()
    check_inbox_markers()
    check_errored_crons()

    # Output JSON
    print(json.dumps(ISSUES, indent=2))


if __name__ == "__main__":
    main()
