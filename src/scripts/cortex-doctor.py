#!/usr/bin/env python3
"""
cortex-doctor.py — Hermes Cortex installation health check

Like 'brew doctor' for Hermes Cortex: single command that checks
repo integrity, cron registration, script existence, service health,
system resources, and config consistency.

Usage:
    python3 cortex-doctor.py                  # full check (default)
    python3 cortex-doctor.py --json           # machine-readable output
    python3 cortex-doctor.py --fix            # auto-fix common issues
    python3 cortex-doctor.py --watch          # re-check every 30s
    python3 cortex-doctor.py --quiet          # compact output

Exit codes: 0 = pass   1 = warn   2 = fail
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────
HOME = Path.home()
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
CORTEX_HOME = Path(os.environ.get("HERMES_CORTEX_HOME", HOME / ".hermes-cortex"))
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
MODELS_ENV = HOME / ".hermes" / "models.env"

# Find cortex repo
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", ""))
if not CORTEX_REPO.is_dir() or not (CORTEX_REPO / "AGENTS.md").exists():
    for candidate in [HOME / "hermes-cortex", HOME / "src" / "hermes-cortex"]:
        if candidate.is_dir() and (candidate / "AGENTS.md").exists():
            CORTEX_REPO = candidate
            break
INSTALL_CRONS = CORTEX_REPO / "src" / "scripts" / "install-crons.sh"
CORTEX_UPDATE = CORTEX_REPO / "src" / "scripts" / "cortex-update.sh"

# Passthrough to subprocess for HTTP checks (avoid cert issues with urllib)
CURL = os.environ.get("CURL_BIN", "curl")
EXTERNAL_BASE = os.environ.get("CORTEX_DOCTOR_BASE", "https://your-domain.com")


# ── Dynamic registries (self-updating from source) ────────────

def parse_expected_crons():
    """Read expected cron names from install-crons.sh's uninstall array.
    This auto-updates whenever install-crons.sh changes."""
    text = read_file(INSTALL_CRONS)
    if not text:
        return []
    # Extract between 'for job in \' and '; do'
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    # Extract quoted strings
    names = re.findall(r'"([^"]+)"', block)
    # Remove 'system-heartbeat' if it still exists in old install-crons.sh
    return [n for n in names if n != "system-heartbeat"]


def find_script_consumers():
    """Scan cortex scripts for models.env variable names.
    Returns dict of {var_name: [matching_scripts]}"""
    scripts_dir = CORTEX_REPO / "src" / "scripts"
    if not scripts_dir.is_dir():
        return {}
    # Known models.env vars to scan for
    known_vars = ["JUDGE_MODEL", "EMBEDDING_MODEL", "CODING_MODEL", "CREATIVE_MODEL", "DEFAULT_MODEL"]
    consumers = {v: [] for v in known_vars}
    for script in sorted(scripts_dir.iterdir()):
        if not script.is_file():
            continue
        text = script.read_text(errors="replace")
        for var in known_vars:
            if var in text:
                consumers[var].append(script.name)
    return consumers

EXTERNAL_SERVICES = [
    ("Dashboard",      f"{EXTERNAL_BASE}:13001/",       "401"),
    ("Langfuse",       f"{EXTERNAL_BASE}:13002/",       "401"),
    ("Inbox API",      f"{EXTERNAL_BASE}:13004/health", "200"),
]

# ── Result tracking ─────────────────────────────────────────────
class Results:
    def __init__(self):
        self.checks = []  # [{name, status, detail, fix}]
        self.pass_count = 0
        self.warn_count = 0
        self.fail_count = 0
        self.json_mode = False
        self.show_fixes = True

    def add(self, name, status, detail="", fix=""):
        self.checks.append({"name": name, "status": status, "detail": detail, "fix": fix})
        if status == "PASS": self.pass_count += 1
        elif status == "WARN": self.warn_count += 1
        elif status == "FAIL": self.fail_count += 1

    def status_icon(self, s):
        if self.json_mode: return s
        return {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ "}.get(s, "❓")

    def print_summary(self, compact=False):
        if self.json_mode:
            print(json.dumps({
                "summary": {"pass": self.pass_count, "warn": self.warn_count, "fail": self.fail_count},
                "checks": self.checks,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
            return

        print(f"\n━━━ Hermes Cortex Doctor ━━━  ({datetime.now().strftime('%H:%M:%S')})\n")

        for c in self.checks:
            icon = self.status_icon(c["status"])
            label = f"{icon} {c['name']}"
            if compact:
                print(f"  {label}")
            else:
                detail = f" — {c['detail']}" if c["detail"] else ""
                print(f"  {label}{detail}")
                if self.show_fixes and c["fix"] and c["status"] != "PASS":
                    print(f"         → {c['fix']}")

        overall = "HEALTHY"
        if self.fail_count > 0:
            overall = "FAILING"
        elif self.warn_count > 0:
            overall = "WARNING"
        icon_map = {"HEALTHY": "✅", "WARNING": "⚠️ ", "FAILING": "❌"}
        print(f"\n  {icon_map[overall]} Overall: {overall}  ({self.pass_count} pass · {self.warn_count} warn · {self.fail_count} fail)\n")


# ── Helpers ─────────────────────────────────────────────────────
def run(cmd, timeout=10):
    """Run a shell command, return (output, exit_code)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except FileNotFoundError:
        return "", -1
    except subprocess.TimeoutExpired:
        return "(timed out)", -1

def http_get(url, timeout=10):
    """Curl-based HTTP check with explicit timeout."""
    out, code = run([CURL, "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url])
    return out.strip()

def read_file(path):
    try:
        return Path(path).read_text()
    except (FileNotFoundError, OSError):
        return ""

def _find_similar_name(name, valid_names):
    """Suggest a similar cron name from valid_names if one exists.
    Checks: missing/extra hyphen, common suffix swaps, single-char diffs."""
    if not name or not valid_names:
        return None

    # Exact after stripping common suffixes
    base = name.replace("-cron", "").replace("-daemon", "").replace("-job", "")
    for v in valid_names:
        if v == name:
            return None  # exact match — not extra
        if v == base:
            return v

    # Hyphen-normalized comparison
    norm = name.replace("_", "-").replace(" ", "-").lower()
    for v in valid_names:
        v_norm = v.replace("_", "-").replace(" ", "-").lower()
        if v_norm == norm:
            return v

    # Single-char Levenshtein distance (insert/delete/substitute)
    for v in valid_names:
        if abs(len(v) - len(name)) <= 2:
            # Count differing characters
            diffs = sum(1 for a, b in zip(v, name) if a != b) + abs(len(v) - len(name))
            if diffs <= 2:
                return v

    # Check if name is expected with a prefix/suffix mismatch
    for v in valid_names:
        if name.startswith(v) or v.startswith(name):
            return v
        if name.endswith(v) or v.endswith(name):
            return v

    return None


# ── Checks ──────────────────────────────────────────────────────

def check_repo(res):
    """1. Repo integrity: on main, clean, up to date."""
    if not CORTEX_REPO.is_dir():
        res.add("Repo exists", "FAIL", f"Not found at {CORTEX_REPO}", "Set CORTEX_REPO env var or clone to ~/hermes-cortex")
        return
    if not (CORTEX_REPO / ".git").is_dir():
        res.add("Repo git", "FAIL", "Not a git repository", "Run: git init or git clone")
        return

    # Branch
    branch, _ = run(["git", "-C", str(CORTEX_REPO), "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "main":
        res.add("Repo branch", "PASS", f"on '{branch}'")
    else:
        res.add("Repo branch", "WARN", f"on '{branch}' not 'main'", "Run: git checkout main")

    # Clean working tree
    status, _ = run(["git", "-C", str(CORTEX_REPO), "status", "--porcelain"])
    if not status:
        res.add("Repo clean", "PASS")
    else:
        lines = status.count("\n") + 1
        res.add("Repo clean", "WARN", f"{lines} uncommitted change(s)", "Run: git status to review")

    # Up to date with origin
    run(["git", "-C", str(CORTEX_REPO), "fetch", "origin", "--quiet"], timeout=15)
    behind, _ = run(["git", "-C", str(CORTEX_REPO), "rev-list", "--count", "HEAD..origin/main"])
    if behind and behind != "0":
        res.add("Repo sync", "WARN", f"{behind} commit(s) behind origin/main", "Run: git pull --rebase")
    else:
        res.add("Repo sync", "PASS", "up to date with origin/main")


def check_crons(res):
    """2. Cron audit: all expected crons registered, workdirs valid, run status."""
    if not JOBS_FILE.exists():
        res.add("Crons file", "FAIL", f"Not found at {JOBS_FILE}", "Run: bash install-crons.sh")
        return

    try:
        data = json.loads(JOBS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        res.add("Crons file", "FAIL", f"Parse error: {e}", "Check ~/.hermes/cron/jobs.json")
        return

    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    registered = {j.get("name"): j for j in jobs if isinstance(j, dict) and j.get("name")}

    # Auto-updating expected cron list from install-crons.sh
    expected_crons = parse_expected_crons()
    if not expected_crons:
        res.add("Crons registry", "WARN", "Could not parse install-crons.sh", "Check src/scripts/install-crons.sh exists")
        expected_crons = list(registered.keys())  # fallback: check whatever exists

    # Check each expected cron
    missing = []
    bad_workdir = []
    stale = []
    for name in expected_crons:
        job = registered.get(name)
        if not job:
            missing.append(name)
            continue

        # Check workdir
        wd = job.get("workdir", "")
        if wd and not os.path.isabs(wd):
            bad_workdir.append((name, wd))

        # Check last run status
        last_status = job.get("last_status", "")
        if last_status and last_status != "ok":
            stale.append((name, last_status))

    if not missing and not bad_workdir and not stale:
        total = len(expected_crons)
        res.add("Crons registered", "PASS", f"all {total} expected crons present and healthy")
    else:
        if missing:
            names = ", ".join(missing)
            res.add("Crons missing", "FAIL", f"{len(missing)} missing: {names}",
                     "Run: bash install-crons.sh --force")
        if bad_workdir:
            for name, wd in bad_workdir:
                res.add(f"Cron workdir ({name})", "FAIL", f"not absolute: '{wd}'",
                         f"Re-create cron with absolute path: cronjob(action='update', job_id=..., workdir='/home/...')")
        if stale:
            for name, st in stale[:3]:
                res.add(f"Cron status ({name})", "WARN", f"last run: {st}",
                         f"Check cron logs: hermes cron logs --name {name}")
            if len(stale) > 3:
                all_names = ", ".join(n for n, _ in stale)
                res.add(f"Cron status ({len(stale)} total)", "WARN", f"unhealthy: {all_names}",
                         "Inspect and re-create unhealthy crons")

    # Check for extra crons — registered but not in expected list
    expected_set = set(expected_crons)
    extra_crons = [n for n in registered if n not in expected_set]
    if extra_crons:
        # Show first 5 individually, summarize the rest
        display = sorted(extra_crons)
        if len(display) <= 5:
            for name in display:
                suggestion = _find_similar_name(name, expected_set)
                if suggestion:
                    res.add(f"Extra cron ({name})", "WARN",
                             f"not part of Hermes Cortex — did you mean '{suggestion}'?",
                             f"Rename or remove: cronjob(action='update', job_id=..., name='{suggestion}')")
                else:
                    res.add(f"Extra cron ({name})", "INFO",
                             f"registered but not part of Hermes Cortex system",
                             f"Remove if unknown: cronjob(action='remove', job_id=...)")
        else:
            # Check if any are near-miss first
            near_misses = [(n, _find_similar_name(n, expected_set)) for n in display[:10]]
            warnings = [(n, s) for n, s in near_misses if s]
            for name, suggestion in warnings[:3]:
                res.add(f"Extra cron ({name})", "WARN",
                         f"not part of Hermes Cortex — did you mean '{suggestion}'?",
                         f"Rename or remove: cronjob(action='update', job_id=..., name='{suggestion}')")
            info_total = len(extra_crons) - len(warnings)
            if info_total > 0:
                res.add(f"Extra crons", "INFO",
                         f"{info_total} cron(s) not part of Hermes Cortex system (e.g. {', '.join(display[:3])}...)",
                         f"Run with full output to see all")

    # Total registered count
    total = len(registered)
    res.add(f"Crons total", "PASS" if total > 0 else "WARN", f"{total} jobs registered"
            if total > 0 else "No cron jobs at all")


def check_scripts(res):
    """3. Script integrity: all scripts referenced by crons exist."""
    if not JOBS_FILE.exists():
        return
    try:
        data = json.loads(JOBS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return

    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    missing_scripts = []
    script_dirs = [
        HERMES_HOME / "scripts",
        CORTEX_HOME / "scripts",
        HOME / ".local" / "bin",
    ]

    for job in jobs:
        if not isinstance(job, dict):
            continue
        script = job.get("script", "")
        if not script:
            continue
        # Check if script exists in any known dir
        found = False
        for d in script_dirs:
            if (d / script).exists():
                found = True
                break
        # Also check as absolute path
        if not found and Path(script).is_absolute():
            if Path(script).exists():
                found = True
        if not found:
            missing_scripts.append((job.get("name", "?"), script))

    if not missing_scripts:
        res.add("Script integrity", "PASS", "all cron scripts found")
    else:
        for name, script in missing_scripts[:5]:
            res.add(f"Script ({name})", "FAIL", f"not found: {script}",
                     f"Run: bash {CORTEX_UPDATE} to deploy scripts")
        if len(missing_scripts) > 5:
            res.add(f"Scripts ({len(missing_scripts)} total)", "FAIL",
                     f"{len(missing_scripts)} referenced scripts missing",
                     "Run: bash cortex-update.sh --force-all")


def check_services(res):
    """4. Service health: external endpoints, Ollama."""
    # External services
    for name, url, expected in EXTERNAL_SERVICES:
        try:
            code = http_get(url, timeout=8)
        except Exception as e:
            res.add(f"Service ({name})", "FAIL", f"Connection error: {e}",
                     "Check nginx: sudo systemctl status nginx")
            continue

        if code == expected:
            res.add(f"Service ({name})", "PASS", f"HTTP {code} (expected)")
        elif code in ("200", "301", "302", "401"):
            # 401 with auth is valid for protected endpoints
            res.add(f"Service ({name})", "PASS", f"HTTP {code} (auth protected)")
        elif code == "000":
            res.add(f"Service ({name})", "FAIL", "Connection refused",
                     "Check nginx: sudo systemctl status nginx")
        else:
            res.add(f"Service ({name})", "WARN", f"HTTP {code} (unexpected)",
                     "Investigate: curl -v {url}")

    # Ollama
    out, _ = run([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
    if out:
        try:
            models = json.loads(out).get("models", [])
            if models:
                res.add("Ollama", "PASS", f"{len(models)} model(s) loaded")
            else:
                res.add("Ollama", "WARN", "Running but no models", "Run: ollama pull <model>")
        except json.JSONDecodeError:
            res.add("Ollama", "WARN", "Responding but not returning model list", "Check: curl http://localhost:11434/api/tags")
    else:
        res.add("Ollama", "FAIL", "Not reachable on localhost:11434", "Run: systemctl --user start ollama || ollama serve")

    # gbrain daemon (cross-platform: systemd on Linux, launchd on macOS)
    if IS_MAC:
        out, _ = run(["launchctl", "list", "com.gbrain.autopilot"], timeout=5)
        if '"PID"' in out:
            res.add("gbrain daemon", "PASS", "autopilot active (launchd)")
        else:
            out2, _ = run(["launchctl", "list", "com.gbrain.sync-watch"], timeout=5)
            if '"PID"' in out2:
                res.add("gbrain daemon", "PASS", "sync-watch active (launchd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                         "Run: bash ~/hermes-cortex/src/scripts/install-gbrain-sync.sh")
    else:  # Linux
        out, _ = run(["systemctl", "--user", "is-active", "gbrain-autopilot"], timeout=5)
        if out.strip() == "active":
            res.add("gbrain daemon", "PASS", "autopilot active (systemd)")
        else:
            out2, _ = run(["systemctl", "--user", "is-active", "com.gbrain.sync-watch"], timeout=5)
            if out2.strip() == "active":
                res.add("gbrain daemon", "PASS", "sync-watch active (systemd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                         "Run: bash ~/hermes-cortex/src/scripts/install-gbrain-sync.sh")


def check_system(res):
    """5. System resources: disk, memory."""
    # Disk
    out, _ = run(["df", "-h", "/"])
    if out:
        lines = out.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[-1].split()
            if len(parts) >= 5:
                used = parts[2]
                avail = parts[3]
                pct = parts[4].rstrip("%")
                try:
                    pct_int = int(pct)
                    status = "PASS" if pct_int < 80 else ("WARN" if pct_int < 90 else "FAIL")
                    res.add(f"Disk usage", status, f"{used} used / {avail} free ({pct}%)",
                             "Free space: sudo journalctl --vacuum-size=500M; sudo apt autoremove" if status != "PASS" else "")
                except ValueError:
                    pass

    # Memory (cross-platform: free on Linux, vm_stat + sysctl on macOS)
    if IS_MAC:
        total_mem, _ = run(["sysctl", "-n", "hw.memsize"], timeout=5)
        if total_mem.isdigit():
            total_gb = int(total_mem) / 1073741824
            vm_out, _ = run(["vm_stat"], timeout=5)
            pages_free = 0
            pages_spec = 0
            pages_purge = 0
            pages_file = 0
            pages_comp = 0
            for line in vm_out.split("\n"):
                m = re.search(r'Pages free:\s+(\d+)', line)
                if m: pages_free = int(m.group(1))
                m = re.search(r'Pages speculative:\s+(\d+)', line)
                if m: pages_spec = int(m.group(1))
                m = re.search(r'Pages purgable:\s+(\d+)', line)
                if m: pages_purge = int(m.group(1))
                m = re.search(r'File-backed pages:\s+(\d+)', line)
                if m: pages_file = int(m.group(1))
                m = re.search(r'Pages occupied by compressor:\s+(\d+)', line)
                if m: pages_comp = int(m.group(1))
            # Approximate: active + wired = used (pages * 16384 / 1073741824 GB)
            total_pages = int(total_mem) / 16384
            used_pages = total_pages - pages_free - pages_spec - pages_purge
            used_gb = used_pages * 16384 / 1073741824
            res.add("Memory", "PASS", f"{used_gb:.1f}G used / {total_gb:.0f}G total")
    else:  # Linux
        out, _ = run(["free", "-h"])
        if out:
            for line in out.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        total = parts[1]
                        used = parts[2]
                        res.add("Memory", "PASS", f"{used} used / {total} total")
                    break

        # /proc/meminfo for percentage warning (Linux only)
        meminfo = read_file("/proc/meminfo")
        mem_total = re.search(r"MemTotal:\s+(\d+)", meminfo)
        mem_avail = re.search(r"MemAvailable:\s+(\d+)", meminfo)
        if mem_total and mem_avail:
            total_kb = int(mem_total.group(1))
            avail_kb = int(mem_avail.group(1))
            pct = int((1 - avail_kb / total_kb) * 100) if total_kb > 0 else 0


def check_config(res):
    """6. Config consistency: models.env var cross-reference."""
    if not MODELS_ENV.exists():
        res.add("Config (models.env)", "WARN", "Not found", "Create ~/.hermes/models.env with env vars")
        return

    text = MODELS_ENV.read_text()
    # Extract defined env vars (KEY=value format, no export keyword required)
    defined = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Match KEY=value or export KEY=value
        m = re.match(r'^(?:export\s+)?(\w+)=(.*)', line)
        if m:
            defined[m.group(1)] = line

    if not defined:
        res.add("Config (models.env)", "WARN", "File exists but no exports defined",
                 "Add JUDGE_MODEL, EMBEDDING_MODEL etc.")
        return

    # Dynamic consumer discovery: scan all src/scripts/ for var references
    consumers_by_var = find_script_consumers()
    for var, consumer_names in consumers_by_var.items():
        if var not in defined:
            res.add(f"Config ({var})", "WARN", f"Not defined in models.env",
                     f"Add: export {var}=<model-name> to ~/.hermes/models.env")
        else:
            if consumer_names:
                res.add(f"Config ({var})", "PASS", f"defined, {len(consumer_names)} consumer(s) found")
            else:
                res.add(f"Config ({var})", "INFO", f"defined but zero consumer scripts reference it")


# ── Fix actions ─────────────────────────────────────────────────
def apply_fixes(res):
    """Attempt to auto-fix common issues."""
    if not res.json_mode:
        print("\n  ── Auto-fix ──\n")

    fixed = 0
    failed = 0

    # Fix 1: If crons missing, run install-crons.sh
    missing_crons = [c for c in res.checks if c["name"].startswith("Crons missing")]
    if missing_crons and INSTALL_CRONS.exists():
        if not res.json_mode:
            print(f"  → Running install-crons.sh --force to recreate missing crons...")
        out, code = run(["bash", str(INSTALL_CRONS), "--force"], timeout=120)
        if code == 0:
            fixed += 1
            if not res.json_mode:
                print(f"  ✅ install-crons.sh completed")
        else:
            failed += 1
            if not res.json_mode:
                print(f"  ❌ install-crons.sh failed (exit {code})")

    # Fix 2: If scripts missing, run cortex-update.sh --force-all
    missing_scripts = [c for c in res.checks if c["name"].startswith("Script")]
    if missing_scripts and CORTEX_UPDATE.exists():
        if not res.json_mode:
            print(f"  → Running cortex-update.sh --force-all to deploy scripts...")
        out, code = run(["bash", str(CORTEX_UPDATE), "--force-all"], timeout=120)
        if code == 0:
            fixed += 1
            if not res.json_mode:
                print(f"  ✅ cortex-update.sh completed")
        else:
            failed += 1
            if not res.json_mode:
                print(f"  ❌ cortex-update.sh failed (exit {code})")

    # Fix 3: If Ollama down, try to start it
    ollama_fail = [c for c in res.checks if c["name"] == "Ollama" and c["status"] == "FAIL"]
    if ollama_fail:
        if not res.json_mode:
            print(f"  → Attempting to start Ollama...")
        out, code = run(["systemctl", "--user", "start", "ollama"], timeout=10)
        if code != 0:
            run(["ollama", "serve"], timeout=5)
        # Check if it came up
        time.sleep(2)
        out2, _ = run([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
        if out2:
            fixed += 1
            if not res.json_mode:
                print(f"  ✅ Ollama started")
        else:
            failed += 1
            if not res.json_mode:
                print(f"  ❌ Could not start Ollama")

    if not res.json_mode:
        print(f"\n  Auto-fix: {fixed} fixed, {failed} failed\n")

    return fixed, failed


# ── Main ─────────────────────────────────────────────────────────
def main():
    args = set(sys.argv[1:])
    res = Results()
    res.json_mode = "--json" in args
    res.show_fixes = "--quiet" not in args
    do_fix = "--fix" in args
    do_watch = "--watch" in args
    compact = "--quiet" in args

    if not res.json_mode:
        print("Hermes Cortex Doctor v1.0")

    if do_watch:
        while True:
            res = Results()
            res.json_mode = False
            res.show_fixes = not compact
            check_repo(res)
            check_crons(res)
            check_scripts(res)
            check_services(res)
            check_system(res)
            check_config(res)
            res.print_summary(compact=compact)
            if res.fail_count > 0:
                print("  ❌ Failing — rechecking in 30s...")
            time.sleep(30)
            # Clear checks for next iteration
    else:
        check_repo(res)
        check_crons(res)
        check_scripts(res)
        check_services(res)
        check_system(res)
        check_config(res)
        res.print_summary(compact=compact)

        if do_fix:
            apply_fixes(res)
            # Re-run checks after fixes
            res2 = Results()
            res2.json_mode = res.json_mode
            res2.show_fixes = res.show_fixes
            check_repo(res2)
            check_crons(res2)
            check_scripts(res2)
            check_services(res2)
            check_system(res2)
            check_config(res2)
            if not res2.json_mode:
                print("\n  ── Post-fix recheck ──")
            res2.print_summary(compact=compact)

    # Exit code
    if res.fail_count > 0:
        sys.exit(2)
    elif res.warn_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
