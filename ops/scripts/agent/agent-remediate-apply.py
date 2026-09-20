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
from hermes_tz import format_timestamp, get_timezone

HOME = Path.home()
STATE_DIR = HOME / ".hermes" / "state"
REMEDIATE_DIR = STATE_DIR / "remediate"
DONE_DIR = REMEDIATE_DIR / "done"
SENSOR_JOB_NAME = "agent-remediation-sensor"
SENSOR_OUTPUT_ROOT = HOME / ".hermes" / "cron" / "output"
SEEN_FILE = STATE_DIR / "remediate-seen.txt"
JOBS_FILE = HOME / ".hermes" / "cron" / "jobs.json"
RESUME_COOLDOWN_FILE = REMEDIATE_DIR / "resume-cooldown.json"
RESUME_COOLDOWN_HOURS = 6
WATCHDOG_STATE_FILE = HOME / ".hermes-cortex" / "state" / "cron-failure-watchdog.json"

# Jobs that must NEVER be auto-resumed, even if a watchdog flag lingers in
# its state file. Cover deliberate/operator holds and superseded duplicates:
#   - agent-hermes-update: fleet-wide pause (see MEMORY) — resume is a
#     deliberate operator action only
#   - orch-backlog-driver: paused on Luke's directive (paused_reason)
#   - the OLD duplicate agent-bus-retry-sweep (d22d6b2a3f47) was superseded by
#     the live one (80dc43b602a9) — resuming it would double-fire the sweep
NEVER_RESUME = {
    "195fa856001d",  # agent-hermes-update
    "dbcdec6bb40d",  # orch-backlog-driver
    "b8c62b635aed",  # check-hermes-upstream-fix
    "d22d6b2a3f47",  # obsolete duplicate agent-bus-retry-sweep
}

KST = get_timezone()

# ── Helpers ─────────────────────────────────────────────────────


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = format_timestamp("[%Y-%m-%d %H:%M %Z]")
    return f"{kst} {name}:"


def kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")


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


def discover_sensor_output_dir() -> Path | None:
    """Find the remediation-sensor cron output dir.

    Job ids are ephemeral (the sensor was recreated under a new id and the
    previously hardcoded SENSOR_JOB_ID went stale, blinding this fixer).
    Canonical path: read jobs.json for the job named agent-remediation-sensor.
    Fallback: the output dir holding the newest .md file.
    """
    jobs_file = HOME / ".hermes" / "cron" / "jobs.json"
    try:
        if jobs_file.exists():
            data = json.loads(jobs_file.read_text(encoding="utf-8"))
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            for j in jobs:
                if j.get("name") == SENSOR_JOB_NAME and j.get("id"):
                    d = SENSOR_OUTPUT_ROOT / str(j["id"])
                    if d.exists():
                        return d
    except Exception as e:
        log(f"⚠️  jobs.json sensor lookup failed: {e}")
    # Fallback: newest .md under the output root
    best, best_mtime = None, 0.0
    if SENSOR_OUTPUT_ROOT.exists():
        for d in SENSOR_OUTPUT_ROOT.iterdir():
            if not d.is_dir():
                continue
            mds = sorted(
                d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            if mds and mds[0].stat().st_mtime > best_mtime:
                best, best_mtime = d, mds[0].stat().st_mtime
    return best


def get_latest_sensor_output(sensor_dir: Path | None) -> str | None:
    """Find and read the most recent remediation-sensor output."""
    if sensor_dir is None or not sensor_dir.exists():
        return None
    files = sorted(sensor_dir.glob("*.md"), reverse=True)
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


# ── Paused-cron auto-resume ─────────────────────────────────────


def _load_resume_cooldown() -> dict:
    if RESUME_COOLDOWN_FILE.exists():
        try:
            return json.loads(RESUME_COOLDOWN_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_resume_cooldown(cd: dict) -> None:
    RESUME_COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESUME_COOLDOWN_FILE.write_text(json.dumps(cd, indent=2), encoding="utf-8")


def maybe_resume_paused_crons() -> list[tuple[str, str]]:
    """Auto-resume crons paused by the failure watchdog once the transient
    failure has cleared. Returns [(name, result_msg), ...].

    Why: agent-cron-failure-watchdog pauses a job after 3 consecutive
    errors but nothing ever resumes it — a transient failure became a
    permanent outage (agent-mycortex-sync sat paused 2 days, 2026-09-18,
    surfacing as endless 'mycortex down' fleet-watchdog alerts).

    Safety: only jobs in state 'paused' (the watchdog/operator pause path)
    are resumed — a plain enabled=false is left alone. A 6h per-job
    cooldown bounds pause/resume flapping: if the job is genuinely broken
    the watchdog re-pauses it after 3 runs and this handler stays quiet
    until the cooldown expires. The cooldown is keyed by job id and
    independent of the sensor seen-file, so a NEW incident after a healthy
    period still triggers a fresh resume.
    """
    results: list[tuple[str, str]] = []
    if not JOBS_FILE.exists():
        return results
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return results
    jobs = data if isinstance(data, list) else data.get("jobs", [])

    # Only jobs the failure-watchdog itself flagged (alerted + hit the
    # 3-strike limit) are candidates — deliberate/operator pauses are never
    # auto-resumed. Respect the NEVER_RESUME denylist on top of that.
    watchdog_alerted = set()
    if WATCHDOG_STATE_FILE.exists():
        try:
            wd = json.loads(WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
            watchdog_alerted = {
                str(jid) for jid, st in wd.items()
                if st.get("alerted") and st.get("consecutive", 0) >= 3
            }
        except (json.JSONDecodeError, OSError):
            watchdog_alerted = set()

    now = datetime.now(timezone.utc)
    cooldown = _load_resume_cooldown()
    dirty = False

    for job in jobs:
        if not isinstance(job, dict) or job.get("state") != "paused":
            continue
        job_id = str(job.get("id") or "")
        name = job.get("name") or job_id
        if not job_id:
            continue
        if job_id in NEVER_RESUME or job_id not in watchdog_alerted:
            continue
        last = cooldown.get(job_id)
        if last:
            try:
                if now - datetime.fromisoformat(last) < timedelta(
                    hours=RESUME_COOLDOWN_HOURS
                ):
                    continue  # cooldown — let the watchdog re-pause cycle finish
            except ValueError:
                pass  # malformed entry — treat as no cooldown
        r = subprocess.run(
            ["hermes", "cron", "resume", job_id],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            cooldown[job_id] = now.isoformat()
            dirty = True
            results.append(
                (job_id, f"✅ Resumed paused cron '{name}' (auto-restore after pause)")
            )
        else:
            results.append(
                (job_id, f"❌ Could not resume paused cron '{name}': "
                         f"{(r.stderr or r.stdout).strip()[:120]}")
            )

    if dirty:
        _save_resume_cooldown(cooldown)
    return results


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
            pass  # expected — silently handled
    
    # Try parsing the whole file as JSON
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass  # expected — silently handled
    
    return []


def make_issue_id(issue: dict) -> str:
    """Generate a stable ID for an issue to prevent re-processing.

    Deliberately excludes the sensor's per-run timestamp: the sensor stamps
    a fresh value every run, so including it made the ID change every run and
    the seen-file dedup never matched — identical failures were re-attempted
    and re-reported every 10 minutes (2026-08-31 regression).
    """
    t = issue.get("type", "unknown")
    d = issue.get("detail", "")
    return f"{t}|{d[:80]}"


def main() -> int:
    seen = load_seen_issues()
    fixed = []
    failed = []
    skipped = []

    # Auto-resume crons paused by the failure watchdog (independent of the
    # sensor seen-file so a later incident can still trigger a fresh resume).
    for rid, msg in maybe_resume_paused_crons():
        if msg.startswith("✅"):
            fixed.append(("paused_cron_restore", msg))
        else:
            failed.append(("paused_cron_restore", msg))
    
    # 1. Read sensor output (job id discovered — ids are ephemeral)
    sensor_dir = discover_sensor_output_dir()
    sensor_text = get_latest_sensor_output(sensor_dir) if sensor_dir else None
    issues = parse_issues(sensor_text) if sensor_text else []
    if issues:
        log(f"📋 Found {len(issues)} issue(s) in sensor output")
    else:
        log("No remediation-sensor issues found" if sensor_dir else "No remediation-sensor output found")

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
