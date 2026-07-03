#!/usr/bin/env python3
"""
cortex-doctor.py — Hermes Cortex installation health check

Like 'brew doctor' for Hermes Cortex: single command that checks
and fixes your entire installation — repo, crons, scripts,
services, system, config, governance (MCP servers, hooks), and
install footprint.

Usage:
    python3 cortex-doctor.py                  # full check (default)
    python3 cortex-doctor.py --json           # machine-readable output
    python3 cortex-doctor.py --fix            # auto-fix everything
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
MODELS_ENV = HERMES_HOME / "models.env"
CONFIG_FILE = HERMES_HOME / "config.yaml"

# Find cortex repo
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", ""))
if not CORTEX_REPO.is_dir() or not (CORTEX_REPO / "AGENTS.md").exists():
    for candidate in [HOME / "hermes-cortex", HOME / "src" / "hermes-cortex"]:
        if candidate.is_dir() and (candidate / "AGENTS.md").exists():
            CORTEX_REPO = candidate
            break
SCRIPTS_SRC = CORTEX_REPO / "src" / "scripts"
INSTALL_CRONS = SCRIPTS_SRC / "install-crons.sh"
CORTEX_UPDATE = SCRIPTS_SRC / "cortex-update.sh"
INSTALL_SCRIPT = CORTEX_REPO / "install.sh"
INSTALL_OLLAMA = SCRIPTS_SRC / "install-ollama.sh"
INSTALL_SCORE_HOOK = SCRIPTS_SRC / "install-score-hook.sh"
SYMLINK_AUDIT = SCRIPTS_SRC / "symlink-audit.sh"
MCP_SERVERS_DIR = CORTEX_REPO / "src" / "mcp-servers"

# Passthrough to subprocess for HTTP checks (avoid cert issues with urllib)
CURL = os.environ.get("CURL_BIN", "curl")
EXTERNAL_BASE = os.environ.get("CORTEX_DOCTOR_BASE", "https://your-domain.com")

# Expected MCP servers
EXPECTED_MCP_SERVERS = {
    "agent-inbox": "inbox-mcp.py",
    "loop-governance": "loop-gov-mcp.py",
}

# External services
EXTERNAL_SERVICES = [
    ("Dashboard",      f"{EXTERNAL_BASE}:13001/",       "401"),
    ("Langfuse",       f"{EXTERNAL_BASE}:13002/",       "401"),
    ("Inbox API",      f"{EXTERNAL_BASE}:13004/health", "200"),
]

# Core install footprint (paths relative to HOME that should exist)
CORE_FOOTPRINT = [
    (".hermes"                                        , "d", "Hermes config directory"),
    (".hermes/cron"                                   , "d", "Cron jobs directory"),
    (".hermes/skills"                                 , "d", "Skills directory"),
    (".hermes/config.yaml"                            , "f", "Hermes configuration"),
    (".hermes-cortex"                                 , "d", "Cortex home directory"),
    (".hermes-cortex/scripts"                         , "d", "Deployed scripts"),
    (".hermes-cortex/state"                           , "d", "State directory"),
    (".hermes-cortex/sessions"                        , "d", "Session archive"),
    (".hermes-cortex/memory"                          , "d", "Agent memory directory"),
    (".local/bin/hermes"                              , "f", "Hermes CLI binary"),
    ("brain"                                          , "d", "Knowledge brain root"),
    ("brain/lessons"                                  , "d", "Lessons directory"),
]


# ── Dynamic registries (self-updating from source) ────────────

def parse_expected_crons():
    """Read expected cron names from install-crons.sh's uninstall array."""
    text = read_file(INSTALL_CRONS)
    if not text:
        return []
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    names = re.findall(r'"([^"]+)"', block)
    return [n for n in names if n != "system-heartbeat"]


def find_script_consumers():
    """Scan cortex scripts for models.env variable names."""
    scripts_dir = CORTEX_REPO / "src" / "scripts"
    if not scripts_dir.is_dir():
        return {}
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


# ── Result tracking ─────────────────────────────────────────────
class Results:
    def __init__(self):
        self.checks = []
        self.pass_count = 0
        self.warn_count = 0
        self.fail_count = 0
        self.info_count = 0
        self.json_mode = False
        self.show_fixes = True

    def add(self, name, status, detail="", fix=""):
        self.checks.append({"name": name, "status": status, "detail": detail, "fix": fix})
        if status == "PASS": self.pass_count += 1
        elif status == "WARN": self.warn_count += 1
        elif status == "FAIL": self.fail_count += 1
        elif status == "INFO": self.info_count += 1

    def status_icon(self, s):
        if self.json_mode: return s
        return {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌", "INFO": "ℹ️ "}.get(s, "❓")

    def print_summary(self, compact=False):
        if self.json_mode:
            print(json.dumps({
                "summary": {"pass": self.pass_count, "warn": self.warn_count, "fail": self.fail_count, "info": self.info_count},
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

        total = self.pass_count + self.warn_count + self.fail_count + self.info_count
        overall = "HEALTHY"
        if self.fail_count > 0:
            overall = "FAILING"
        elif self.warn_count > 0:
            overall = "WARNING"
        icon_map = {"HEALTHY": "✅", "WARNING": "⚠️ ", "FAILING": "❌"}
        print(f"\n  {icon_map[overall]} Overall: {overall}  ({self.pass_count} pass · {self.warn_count} warn · {self.fail_count} fail · {self.info_count} info)\n")


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


def run_bg(cmd, timeout=10):
    """Run command, return output, ignore errors."""
    out, _ = run(cmd, timeout=timeout)
    return out


def http_get(url, timeout=10):
    """Curl-based HTTP check."""
    out, _ = run([CURL, "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url])
    return out.strip()


def read_file(path):
    try:
        return Path(path).read_text()
    except (FileNotFoundError, OSError):
        return ""


def process_running(name):
    """Check if a process matching name is running."""
    out = run_bg(["pgrep", "-f", name], timeout=5)
    return bool(out.strip())


def _find_similar_name(name, valid_names):
    """Suggest a similar cron name from valid_names if one exists."""
    if not name or not valid_names:
        return None
    base = name.replace("-cron", "").replace("-daemon", "").replace("-job", "")
    for v in valid_names:
        if v == name:
            return None
        if v == base:
            return v
    norm = name.replace("_", "-").replace(" ", "-").lower()
    for v in valid_names:
        v_norm = v.replace("_", "-").replace(" ", "-").lower()
        if v_norm == norm:
            return v
    for v in valid_names:
        if abs(len(v) - len(name)) <= 2:
            diffs = sum(1 for a, b in zip(v, name) if a != b) + abs(len(v) - len(name))
            if diffs <= 2:
                return v
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
        res.add("Repo exists", "FAIL", f"Not found at {CORTEX_REPO}",
                "Set CORTEX_REPO env var or clone to ~/hermes-cortex")
        return
    if not (CORTEX_REPO / ".git").is_dir():
        res.add("Repo git", "FAIL", "Not a git repository", "Run: git init or git clone")
        return

    branch = run_bg(["git", "-C", str(CORTEX_REPO), "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "main":
        res.add("Repo branch", "PASS", f"on '{branch}'")
    else:
        res.add("Repo branch", "WARN", f"on '{branch}' not 'main'", "Run: git checkout main")

    status = run_bg(["git", "-C", str(CORTEX_REPO), "status", "--porcelain"])
    if not status:
        res.add("Repo clean", "PASS")
    else:
        lines = status.count("\n") + 1
        res.add("Repo clean", "WARN", f"{lines} uncommitted change(s)", "Run: git status to review")

    run(["git", "-C", str(CORTEX_REPO), "fetch", "origin", "--quiet"], timeout=15)
    behind = run_bg(["git", "-C", str(CORTEX_REPO), "rev-list", "--count", "HEAD..origin/main"])
    if behind and behind != "0":
        res.add("Repo sync", "WARN", f"{behind} commit(s) behind origin/main", "Run: git pull --rebase")
    else:
        res.add("Repo sync", "PASS", "up to date with origin/main")


def check_crons(res):
    """2. Cron audit: all expected crons registered, workdirs valid, run status, extra crons."""
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

    expected_crons = parse_expected_crons()
    if not expected_crons:
        res.add("Crons registry", "WARN", "Could not parse install-crons.sh",
                "Check src/scripts/install-crons.sh exists")
        expected_crons = list(registered.keys())

    missing = []
    bad_workdir = []
    stale = []
    for name in expected_crons:
        job = registered.get(name)
        if not job:
            missing.append(name)
            continue
        wd = job.get("workdir", "")
        if wd and not os.path.isabs(wd):
            bad_workdir.append((name, wd))
        last_status = job.get("last_status", "")
        if last_status and last_status != "ok":
            stale.append((name, last_status))

    if not missing and not bad_workdir and not stale:
        res.add("Crons registered", "PASS", f"all {len(expected_crons)} expected crons present and healthy")
    else:
        if missing:
            res.add("Crons missing", "FAIL", f"{len(missing)} missing: {', '.join(missing)}",
                     "Run: bash install-crons.sh --force")
        if bad_workdir:
            for name, wd in bad_workdir[:3]:
                res.add(f"Cron workdir ({name})", "FAIL", f"not absolute: '{wd}'",
                         f"Re-create cron with absolute path")
        if stale:
            for name, st in stale[:3]:
                res.add(f"Cron status ({name})", "WARN", f"last run: {st}",
                         f"Check: hermes cron logs --name {name}")
            if len(stale) > 3:
                res.add(f"Cron status ({len(stale)} total)", "WARN", f"unhealthy crons",
                         "Inspect and re-create unhealthy crons")

    # Extra crons
    expected_set = set(expected_crons)
    extra = [str(n) for n in registered if n not in expected_set]
    if extra:
        display = sorted(extra)
        if len(display) <= 5:
            for name in display:
                suggestion = _find_similar_name(name, expected_set)
                status = "WARN" if suggestion else "INFO"
                detail = f"did you mean '{suggestion}'?" if suggestion else "not part of Hermes Cortex"
                res.add(f"Extra cron ({name})", status, detail)
        else:
            near_misses = [(n, _find_similar_name(n, expected_set)) for n in display[:10]]
            warnings = [(n, s) for n, s in near_misses if s]
            for name, suggestion in warnings[:3]:
                res.add(f"Extra cron ({name})", "WARN", f"did you mean '{suggestion}'?")
            info_total = len(extra) - len(warnings)
            if info_total > 0:
                res.add("Extra crons", "INFO", f"{info_total} cron(s) not part of system (e.g. {', '.join(display[:3])}...)")

    res.add("Crons total", "PASS" if len(registered) > 0 else "WARN", f"{len(registered)} jobs registered")


def check_scripts(res):
    """3. Script integrity: all scripts referenced by crons exist."""
    if not JOBS_FILE.exists():
        return
    try:
        data = json.loads(JOBS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return

    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    script_dirs = [HERMES_HOME / "scripts", CORTEX_HOME / "scripts", HOME / ".local" / "bin"]
    missing = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        script = job.get("script", "")
        if not script:
            continue
        found = False
        for d in script_dirs:
            if (d / script).exists():
                found = True
                break
        if not found and Path(script).is_absolute() and Path(script).exists():
            found = True
        if not found:
            missing.append((job.get("name", "?"), script))

    if not missing:
        res.add("Script integrity", "PASS", "all cron scripts found")
    else:
        for name, script in missing[:5]:
            res.add(f"Script ({name})", "FAIL", f"not found: {script}", "Run: bash cortex-update.sh --force-all")


def check_services(res):
    """4. Service health: external endpoints, Ollama, gbrain."""
    for name, url, expected in EXTERNAL_SERVICES:
        try:
            code = http_get(url, timeout=8)
        except Exception as e:
            res.add(f"Service ({name})", "FAIL", f"Connection error: {e}", "Check nginx")
            continue
        if code == expected or code in ("200", "301", "302", "401"):
            res.add(f"Service ({name})", "PASS", f"HTTP {code}")
        elif code == "000":
            res.add(f"Service ({name})", "FAIL", "Connection refused", "Check nginx")
        else:
            res.add(f"Service ({name})", "WARN", f"HTTP {code} (unexpected)")

    # Ollama
    out = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
    if out:
        try:
            models = json.loads(out).get("models", [])
            if models:
                res.add("Ollama", "PASS", f"{len(models)} model(s) loaded")
            else:
                res.add("Ollama", "WARN", "Running but no models", "Run: ollama pull <model>")
        except json.JSONDecodeError:
            res.add("Ollama", "WARN", "Responding but not returning model list")
    else:
        res.add("Ollama", "FAIL", "Not reachable on localhost:11434",
                "Run: systemctl --user start ollama || ollama serve")

    # gbrain daemon
    if IS_MAC:
        out = run_bg(["launchctl", "list", "com.gbrain.autopilot"], timeout=5)
        if '"PID"' in out:
            res.add("gbrain daemon", "PASS", "autopilot active (launchd)")
        else:
            out2 = run_bg(["launchctl", "list", "com.gbrain.sync-watch"], timeout=5)
            if '"PID"' in out2:
                res.add("gbrain daemon", "PASS", "sync-watch active (launchd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                         "Run: bash ~/hermes-cortex/src/scripts/install-gbrain-sync.sh")
    else:
        out = run_bg(["systemctl", "--user", "is-active", "gbrain-autopilot"], timeout=5)
        if out.strip() == "active":
            res.add("gbrain daemon", "PASS", "autopilot active (systemd)")
        else:
            out2 = run_bg(["systemctl", "--user", "is-active", "com.gbrain.sync-watch"], timeout=5)
            if out2.strip() == "active":
                res.add("gbrain daemon", "PASS", "sync-watch active (systemd, legacy)")
            else:
                res.add("gbrain daemon", "WARN", "Neither autopilot nor sync-watch active",
                         "Run: bash ~/hermes-cortex/src/scripts/install-gbrain-sync.sh")


def check_system(res):
    """5. System resources: disk, memory."""
    out = run_bg(["df", "-h", "/"])
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
                    if pct_int < 80:
                        status = "PASS"
                        fix = ""
                    elif pct_int < 90:
                        status = "WARN"
                        fix = "Free space: sudo journalctl --vacuum-size=500M; sudo apt autoremove"
                    else:
                        status = "FAIL"
                        fix = "Free space: sudo journalctl --vacuum-size=500M; sudo apt autoremove"
                    res.add("Disk usage", status, f"{used} used / {avail} free ({pct}%)", fix)
                except ValueError:
                    pass

    if IS_MAC:
        total_mem = run_bg(["sysctl", "-n", "hw.memsize"], timeout=5)
        if total_mem.isdigit():
            total_gb = int(total_mem) / 1073741824
            vm_out = run_bg(["vm_stat"], timeout=5)
            pages_free = pages_spec = pages_purge = 0
            for line in vm_out.split("\n"):
                m = re.search(r'Pages free:\s+(\d+)', line)
                if m: pages_free = int(m.group(1))
                m = re.search(r'Pages speculative:\s+(\d+)', line)
                if m: pages_spec = int(m.group(1))
                m = re.search(r'Pages purgable:\s+(\d+)', line)
                if m: pages_purge = int(m.group(1))
            total_pages = int(total_mem) / 16384
            used_pages = total_pages - pages_free - pages_spec - pages_purge
            used_gb = used_pages * 16384 / 1073741824
            res.add("Memory", "PASS", f"{used_gb:.1f}G used / {total_gb:.0f}G total")
    else:
        out = run_bg(["free", "-h"])
        if out:
            for line in out.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        res.add("Memory", "PASS", f"{parts[2]} used / {parts[1]} total")
                    break


def check_config(res):
    """6. Config consistency: models.env var cross-reference."""
    if not MODELS_ENV.exists():
        res.add("Config (models.env)", "WARN", "Not found", "Create ~/.hermes/models.env with env vars")
        return

    text = MODELS_ENV.read_text()
    defined = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(?:export\s+)?(\w+)=(.*)', line)
        if m:
            defined[m.group(1)] = line

    if not defined:
        res.add("Config (models.env)", "WARN", "File exists but no exports defined",
                 "Add JUDGE_MODEL, EMBEDDING_MODEL etc.")
        return

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


def check_governance(res):
    """7. Governance system: MCP servers, pre-commit hook, score-cycle, governance lock."""
    config_text = read_file(CONFIG_FILE)

    # MCP servers in config.yaml
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if name in config_text:
            res.add(f"MCP server ({name})", "PASS", "configured in config.yaml")
        else:
            res.add(f"MCP server ({name})", "FAIL", "not configured",
                     f"Add to config.yaml under mcpServers: {name}")

    # MCP servers running
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if process_running(server_script):
            res.add(f"MCP running ({name})", "PASS", "process active")
        else:
            res.add(f"MCP running ({name})", "WARN", "not running (may start on demand)",
                     "Check: systemctl or hermes process status")

    # Pre-commit hook
    hook_path = CORTEX_REPO / ".git" / "hooks" / "pre-commit"
    if hook_path.exists():
        content = hook_path.read_text()
        if "score-cycle" in content or "governance" in content:
            res.add("Pre-commit hook", "PASS", "installed with governance check")
        else:
            res.add("Pre-commit hook", "WARN", "installed but may be outdated",
                     "Run: bash install-score-hook.sh")
    else:
        res.add("Pre-commit hook", "WARN", "not installed",
                 "Run: bash install-score-hook.sh for governance enforcement")

    # Pre-push hook
    push_hook_path = CORTEX_REPO / ".git" / "hooks" / "pre-push"
    if push_hook_path.exists():
        push_content = push_hook_path.read_text()
        if "pre-push-pull" in push_content:
            res.add("Pre-push hook", "PASS", "installed with pull-before-push check")
        else:
            res.add("Pre-push hook", "WARN", "installed but may be outdated",
                     "Run: bash install-score-hook.sh")
    else:
        res.add("Pre-push hook", "WARN", "not installed",
                 "Run: bash install-score-hook.sh for push protection")

    # Score-cycle
    score_paths = [
        HOME / ".local" / "bin" / "score-cycle",
        Path("/usr/local/bin/score-cycle"),
        CORTEX_HOME / "scripts" / "score-cycle",
    ]
    if any(p.exists() for p in score_paths):
        res.add("Score-cycle", "PASS", "available in PATH")
    else:
        res.add("Score-cycle", "WARN", "not found in PATH",
                 "Run: bash install-score-hook.sh to deploy scoring tools")

    # Stuck governance lock
    lock_file = CORTEX_HOME / "state" / ".governance-active.json"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            started = lock_data.get("started_at", "unknown")
            res.add("Governance lock", "WARN", f"stale lock from {started}",
                     "Remove: rm -f ~/.hermes-cortex/state/.governance-active.json")
        except (json.JSONDecodeError, OSError):
            res.add("Governance lock", "WARN", "stale lock file (unparseable)",
                     "Remove: rm -f ~/.hermes-cortex/state/.governance-active.json")
    else:
        res.add("Governance lock", "PASS", "no stale lock")


def check_install(res):
    """8. Install footprint: core files and directories present."""
    missing = []
    for rel_path, kind, desc in CORE_FOOTPRINT:
        p = HOME / rel_path
        if kind == "d" and not p.is_dir():
            missing.append((desc, rel_path))
        elif kind == "f" and not p.is_file():
            missing.append((desc, rel_path))

    if not missing:
        res.add("Install footprint", "PASS", "all core paths present")
    else:
        for desc, rel_path in missing[:5]:
            res.add(f"Install ({desc})", "FAIL", f"missing: {rel_path}",
                     f"Run: bash {INSTALL_SCRIPT}")
        if len(missing) > 5:
            res.add(f"Install ({len(missing)} missing)", "FAIL", f"run install.sh to fix")

    # Symlink audit
    if SYMLINK_AUDIT.exists():
        out = run_bg(["bash", str(SYMLINK_AUDIT)], timeout=15)
        if "BROKEN" in out or "MISMATCH" in out:
            res.add("Symlinks", "WARN", "some symlinks need attention",
                     "Run: bash ~/hermes-cortex/src/scripts/symlink-audit.sh")
        elif "ALL OK" in out or "OK" in out:
            res.add("Symlinks", "PASS", "all symlinks valid")
        else:
            res.add("Symlinks", "INFO", "symlink audit ran (check output manually)")


# ── Fix actions ─────────────────────────────────────────────────
def _run_fix(description, cmd, timeout=120):
    """Helper: print description, run command, return True on success."""
    print(f"  → {description}...")
    out, code = run(cmd, timeout=timeout)
    if code == 0:
        print(f"  ✅ Done")
        return True
    else:
        print(f"  ❌ Failed (exit {code})")
        if out:
            for line in out.split("\n")[:5]:
                print(f"     {line}")
        return False


def apply_fixes(res):
    """Attempt to auto-fix every issue found."""
    if not res.json_mode:
        print("\n  ── Auto-fix ──\n")

    fixed = 0
    failed = 0
    fix_map = {c["name"]: c["status"] for c in res.checks}

    # Fix: missing crons → install-crons.sh
    if any("Crons missing" in k for k in fix_map):
        if _run_fix("Recreating missing crons", ["bash", str(INSTALL_CRONS), "--force"]):
            fixed += 1
        else:
            failed += 1

    # Fix: missing scripts → cortex-update.sh
    if any(k.startswith("Script") for k in fix_map):
        if _run_fix("Deploying scripts via cortex-update", ["bash", str(CORTEX_UPDATE), "--force-all"]):
            fixed += 1
        else:
            failed += 1

    # Fix: MCP server not configured
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if f"MCP server ({name})" in fix_map and fix_map[f"MCP server ({name})"] == "FAIL":
            if CONFIG_FILE.exists() and CORTEX_REPO.exists():
                mcp_path = MCP_SERVERS_DIR / server_script
                if mcp_path.exists():
                    if _run_fix(f"Adding MCP server {name} to config.yaml",
                                ["python3", "-c", f"""
import yaml, sys
with open('{CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
if 'mcpServers' not in cfg:
    cfg['mcpServers'] = {{}}
cfg['mcpServers']['{name}'] = {{
    'command': 'python3',
    'args': ['{mcp_path}'],
    'enabled': True
}}
with open('{CONFIG_FILE}', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('ADDED')
"""]):
                        fixed += 1
                    else:
                        failed += 1

    # Fix: pre-commit hook not installed
    if "Pre-commit hook" in fix_map and "not installed" in str(fix_map["Pre-commit hook"]):
        if INSTALL_SCORE_HOOK.exists():
            if _run_fix("Installing pre-commit hook",
                         ["bash", str(INSTALL_SCORE_HOOK), "--path", str(CORTEX_REPO)]):
                fixed += 1
            else:
                failed += 1

    # Fix: pre-push hook not installed or outdated
    if "Pre-push hook" in fix_map and "not installed" in str(fix_map.get("Pre-push hook", "")):
        if INSTALL_SCORE_HOOK.exists():
            if _run_fix("Installing pre-push hook",
                         ["bash", str(INSTALL_SCORE_HOOK), "--path", str(CORTEX_REPO)]):
                fixed += 1
            else:
                failed += 1

    # Fix: stuck governance lock
    if "Governance lock" in fix_map and "stale" in fix_map["Governance lock"]:
        lock_file = CORTEX_HOME / "state" / ".governance-active.json"
        if lock_file.exists():
            lock_file.unlink()
            print(f"  → Removing stale governance lock...")
            print(f"  ✅ Done")
            fixed += 1

    # Fix: Ollama down
    if "Ollama" in fix_map and fix_map["Ollama"] == "FAIL":
        if _run_fix("Starting Ollama", ["systemctl", "--user", "start", "ollama"], timeout=10):
            time.sleep(2)
            out2 = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
            if out2:
                fixed += 1
            else:
                failed += 1
        else:
            # Try direct serve as fallback
            if _run_fix("Starting Ollama directly (ollama serve)", ["ollama", "serve"], timeout=5):
                time.sleep(2)
                fixed += 1
            else:
                failed += 1

    # Fix: symlinks need attention
    if "Symlinks" in fix_map and fix_map["Symlinks"] == "WARN":
        if SYMLINK_AUDIT.exists():
            if _run_fix("Running symlink audit", ["bash", str(SYMLINK_AUDIT)]):
                fixed += 1
            else:
                failed += 1

    # Fix: install footprint missing → run install.sh core
    if any(k.startswith("Install (") for k in fix_map):
        if INSTALL_SCRIPT.exists():
            if _run_fix("Running install.sh core components",
                         ["bash", str(INSTALL_SCRIPT), "--quick"]):
                fixed += 1
            else:
                failed += 1

    # Fix: model context (only if 3b variant detected below threshold)
    if INSTALL_OLLAMA.exists():
        out = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
        if out:
            try:
                models = json.loads(out).get("models", [])
                for m in models:
                    mname = m.get("name", "")
                    if "qwen2.5-coder:3b" in mname or mname == "qwen2.5-coder:3b":
                        if _run_fix(f"Checking context for {mname}",
                                     ["bash", str(INSTALL_OLLAMA), "build_qwen", mname]):
                            fixed += 1
                        break
            except (json.JSONDecodeError, KeyError):
                pass

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

    all_checks = [check_repo, check_crons, check_scripts, check_services,
                   check_system, check_config, check_governance, check_install]

    if not res.json_mode:
        print("Hermes Cortex Doctor v2.0")

    if do_watch:
        while True:
            res = Results()
            res.json_mode = False
            res.show_fixes = not compact
            for fn in all_checks:
                fn(res)
            res.print_summary(compact=compact)
            time.sleep(30)
    else:
        for fn in all_checks:
            fn(res)
        res.print_summary(compact=compact)

        if do_fix:
            apply_fixes(res)
            # Re-run checks after fixes
            res2 = Results()
            res2.json_mode = res.json_mode
            res2.show_fixes = res.show_fixes
            for fn in all_checks:
                fn(res2)
            if not res2.json_mode:
                print("\n  ── Post-fix recheck ──")
            res2.print_summary(compact=compact)

    if res.fail_count > 0:
        sys.exit(2)
    elif res.warn_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
