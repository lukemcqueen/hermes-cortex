#!/usr/bin/env python3
"""agent-remediate-apply.py — no_agent cron script.

Reads the latest remediation-sensor output and applies deterministic fixes
for common issues. Runs every 10 minutes.

Silent when no issues found or all issues already handled.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes" / "state"
REMEDIATE_DIR = STATE_DIR / "remediate"
DONE_DIR = REMEDIATE_DIR / "done"
SENSOR_JOB_ID = "900f19048af7"  # remediation-sensor
SENSOR_OUTPUT_DIR = HOME / ".hermes" / "cron" / "output" / SENSOR_JOB_ID
SEEN_FILE = STATE_DIR / "remediate-seen.txt"

KST = timezone(timedelta(hours=9))

# ── Helpers ─────────────────────────────────────────────────────


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = datetime.now(timezone(timedelta(hours=9))).strftime(
        "[%Y-%m-%d %H:%M KST]"
    )
    return f"{kst} {name}:"


def kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def log(msg: str):
    print(msg, file=sys.stderr)


def run_cmd(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            shell=True, executable="/bin/bash",
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1


def get_latest_sensor_output() -> str | None:
    """Find and read the most recent remediation-sensor output."""
    if not SENSOR_OUTPUT_DIR.exists():
        return None
    files = sorted(SENSOR_OUTPUT_DIR.glob("*.md"), reverse=True)
    if not files:
        return None
    return files[0].read_text(encoding="utf-8", errors="replace")


def load_seen_issues() -> set[str]:
    if SEEN_FILE.exists():
        return {line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip()}
    return set()


def save_seen_issues(ids: set[str]):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text("\n".join(sorted(ids)) + "\n")


# ── Fix Functions ───────────────────────────────────────────────


def fix_nginx_issue(context: dict) -> str | None:
    """Check nginx config and reload if needed."""
    log("🔧 Checking nginx...")
    ok, err, rc = run_cmd("nginx -t 2>&1")
    if rc != 0:
        log(f"  nginx config invalid: {err[:200]}")
        return None
    ok, err, rc = run_cmd("nginx -s reload 2>&1")
    if rc == 0:
        return "✅ nginx config validated and reloaded"
    log(f"  nginx reload failed: {err[:200]}")
    return None


def fix_service_restart(context: dict) -> str | None:
    """Restart a service that was reported as down."""
    service = context.get("service", "")
    if not service:
        return None
    log(f"🔧 Restarting service: {service}")
    ok, err, rc = run_cmd(f"sudo systemctl restart {service} 2>&1 || sudo service {service} restart 2>&1")
    if rc == 0:
        return f"✅ Restarted service: {service}"
    log(f"  Failed to restart {service}: {err[:200]}")
    return None


def fix_web_cache_cleanup(context: dict) -> str | None:
    """Clean up large web cache."""
    cache_path = HOME / ".hermes" / "data" / "web_cache.sqlite"
    if not cache_path.exists():
        return None
    size_mb = cache_path.stat().st_size / (1024 * 1024)
    if size_mb < 50:
        return None  # Not large enough to warrant action
    log(f"🔧 Web cache is {size_mb:.0f}MB — vacuuming...")
    ok, err, rc = run_cmd(f"sqlite3 {cache_path} 'VACUUM;' 2>&1")
    if rc == 0:
        new_size = cache_path.stat().st_size / (1024 * 1024)
        return f"✅ Web cache vacuumed: {size_mb:.0f}MB → {new_size:.0f}MB"
    return None


def fix_ollama_stale(context: dict) -> str | None:
    """Check if Ollama is running and responsive."""
    ok, err, rc = run_cmd("curl -sf http://localhost:11434/api/tags > /dev/null 2>&1")
    if rc == 0:
        return None  # Already healthy
    log("🔧 Ollama not responding — checking process...")
    ok, err, rc = run_cmd("pgrep -x ollama > /dev/null 2>&1")
    if rc == 0:
        # Process exists but not responding — try restart
        ok, err, rc = run_cmd("killall -SIGTERM ollama 2>&1; sleep 2; ollama serve > /dev/null 2>&1 &")
        return "⚠️ Ollama process restarted (SIGTERM + re-launch)"
    # Not running at all — start it
    ok, err, rc = run_cmd("ollama serve > /dev/null 2>&1 &")
    return "⚠️ Ollama started (was not running)"


def fix_disk_space(context: dict) -> str | None:
    """Check disk usage and clean apt cache if needed."""
    ok, err, rc = run_cmd("df / | tail -1 | awk '{print $5}' | tr -d '%'")
    if not ok or rc != 0:
        return None
    try:
        pct = int(ok)
    except ValueError:
        return None
    if pct < 80:
        return None  # Not critical
    log(f"🔧 Disk at {pct}% — cleaning apt cache...")
    ok, err, rc = run_cmd("sudo apt-get clean -qq 2>&1")
    if rc == 0:
        new_ok, _, _ = run_cmd("df / | tail -1 | awk '{print $5}' | tr -d '%'")
        return f"✅ Apt cache cleaned. Disk: {pct}% → {new_ok}%"
    log(f"  apt clean failed: {err[:200]}")
    return None


# ── Issue Router ────────────────────────────────────────────────

FIX_HANDLERS = {
    "nginx_issue": fix_nginx_issue,
    "service_down": fix_service_restart,
    "web_cache_large": fix_web_cache_cleanup,
    "ollama_down": fix_ollama_stale,
    "disk_low": fix_disk_space,
    "disk_high": fix_disk_space,
}


def parse_issues(text: str) -> list[dict]:
    """Parse JSON issue array from sensor output."""
    # The sensor output is a markdown file wrapping JSON. Try to extract JSON array.
    # First try direct JSON parse
    text = text.strip()
    
    # Try to find a JSON array in the text
    array_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Try parsing the whole file as JSON
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    
    return []


def make_issue_id(issue: dict) -> str:
    """Generate a unique ID for an issue to prevent re-processing."""
    t = issue.get("type", "unknown")
    d = issue.get("detail", "")
    ts = issue.get("timestamp", "")
    return f"{t}|{d[:80]}|{ts}"


def main() -> int:
    seen = load_seen_issues()
    fixed = []
    failed = []
    skipped = []
    
    # 1. Read sensor output
    sensor_text = get_latest_sensor_output()
    if not sensor_text:
        log("No sensor output found — nothing to do")
        return 0
    
    issues = parse_issues(sensor_text)
    if not issues:
        log("No issues in sensor output — system healthy")
        return 0
    
    log(f"📋 Found {len(issues)} issue(s) in sensor output")
    
    # 2. Process each issue
    for issue in issues:
        issue_id = make_issue_id(issue)
        if issue_id in seen:
            skipped.append(issue)
            continue
        
        typ = issue.get("type", "")
        handler = FIX_HANDLERS.get(typ)
        
        if not handler:
            log(f"  ⏭️ No handler for type '{typ}' — skipping")
            skipped.append(issue)
            seen.add(issue_id)
            continue
        
        log(f"  🔧 Handling {typ}...")
        result = handler(issue.get("context", {}))
        
        if result:
            fixed.append((typ, result))
            log(f"    ✅ {result}")
        else:
            failed.append((typ, issue.get("detail", "")))
            log(f"    ❌ Could not fix {typ}")
        
        seen.add(issue_id)
    
    # 3. Save seen IDs
    save_seen_issues(seen)
    
    # 4. Output report if anything was done
    if not fixed:
        if failed:
            print(f"[{kst_now()}] agent-remediate-apply:")
            print(f"  ❌ {len(failed)} issue(s) could not be fixed")
            for typ, detail in failed:
                print(f"     - {typ}: {detail[:120]}")
            return 0
        # Nothing to report — silent
        return 0

    print(f"[{kst_now()}] agent-remediate-apply:")
    for typ, result in fixed:
        print(f"  ✅ [{typ}] {result}")
    if failed:
        print()
        print(f"  ❌ {len(failed)} issue(s) could not be fixed:")
        for typ, detail in failed:
            print(f"     - {typ}: {detail[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
