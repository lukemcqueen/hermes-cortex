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
MODELS_ENV = HOME / "hermes-cortex" / ".env"
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
INSTALL_ORCH_CRONS = SCRIPTS_SRC / "install" / "install-orch-crons.sh"
INSTALL_SCRIPT = CORTEX_REPO / "install.sh"
INSTALL_OLLAMA = SCRIPTS_SRC / "install-ollama.sh"
INSTALL_SCORE_HOOK = SCRIPTS_SRC / "install-score-hook.sh"
SYMLINK_AUDIT = SCRIPTS_SRC / "symlink-audit.sh"
MCP_SERVERS_DIR = CORTEX_REPO / "src" / "mcp-servers"

# Passthrough to subprocess for HTTP checks (avoid cert issues with urllib)
CURL = os.environ.get("CURL_BIN", "curl")
EXTERNAL_BASE = os.environ.get("CORTEX_DOCTOR_BASE", "")
# Fall back to localhost when no domain is configured (PII-safe default)
if not EXTERNAL_BASE:
    EXTERNAL_BASE = "https://localhost"

# Port prefix — read from CORTEX_HOME/.env, default to 13
_PORT_PREFIX_ENV = CORTEX_HOME / ".env"
_PORT_PREFIX = "13"  # default
try:
    for _line in _PORT_PREFIX_ENV.read_text().split("\n"):
        _line = _line.strip()
        if _line.startswith("CORTEX_NGINX_PORT_PREFIX="):
            _val = _line.split("=", 1)[1].strip().strip('"').strip("'")
            if _val:
                _PORT_PREFIX = _val
except (FileNotFoundError, OSError, IndexError):
    pass

# Expected MCP servers
EXPECTED_MCP_SERVERS = {
    "agent-inbox": "inbox-mcp.py",
    "loop-governance": "loop-gov-mcp.py",
}

# External services — port is derived from CORTEX_NGINX_PORT_PREFIX
EXTERNAL_SERVICES = [
    ("Dashboard",      f"{EXTERNAL_BASE}:{_PORT_PREFIX}001/",       "401"),
    ("Langfuse",       f"{EXTERNAL_BASE}:{_PORT_PREFIX}002/",       "401"),
    ("Inbox API",      f"{EXTERNAL_BASE}:{_PORT_PREFIX}004/health", "200"),
]

# Core install footprint (paths relative to HOME that should exist)
CORE_FOOTPRINT = [
    (".hermes"                                        , "d", "Hermes config directory"),
    (".hermes/cron"                                   , "d", "Cron jobs directory"),
    (".hermes/skills"                                 , "d", "Skills directory"),
    (".hermes/config.yaml"                            , "f", "Hermes configuration"),
    (".hermes-cortex"                                 , "d", "Cortex home directory"),
    (".hermes-cortex/scripts"                         , "d", "Deployed scripts"),
    (".hermes-cortex/sessions"                        , "d", "Session archive"),
    (".hermes-cortex/hooks"                          , "d", "Shared hooks directory"),
    (".hermes-cortex/state"                           , "d", "State directory"),
    (".hermes-cortex/memory"                          , "d", "Agent memory directory"),
    (".local/bin/hermes"                              , "f", "Hermes CLI binary"),
    ("brain"                                          , "d", "Knowledge brain root"),
    ("brain/lessons"                                  , "d", "Lessons directory"),
]


# ── Dynamic registries (self-updating from source) ────────────

def parse_expected_crons():
    """Read expected universal cron names from install-crons.sh's uninstall array,
    excluding orchestrator-only crons (those in install-orch-crons.sh)."""
    text = read_file(INSTALL_CRONS)
    if not text:
        return []
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    names = re.findall(r'"([^"]+)"', block)
    # Exclude system-heartbeat (removed from active installs)
    # and orchestrator-only crons (validated separately)
    orch_crons = set(parse_orch_crons())
    return [n for n in names if n != "system-heartbeat" and n not in orch_crons]


def parse_orch_crons():
    """Read orchestrator-only cron names from install-orch-crons.sh."""
    text = read_file(INSTALL_ORCH_CRONS)
    if not text:
        return []
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    return re.findall(r'"([^"]+)"', block)


def find_script_consumers():
    """Scan cortex scripts for .env variable names."""
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
    """Curl-based HTTP check (with -k for localhost SSL)."""
    out, _ = run([CURL, "-sk", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url])
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

    # ── Orchestrator-only crons ──
    # Validate separately: only expected on orchestrator machines
    orch_crons = parse_orch_crons()
    hostname = run_bg(["hostname", "-s"]).strip() or "unknown"
    is_orch = hostname in ("moses", "esther")
    if orch_crons:
        missing_orch = [n for n in orch_crons if n not in registered]
        if is_orch and missing_orch:
            res.add("Orch crons missing", "FAIL",
                    f"orchestrator host '{hostname}' missing {len(missing_orch)}: {', '.join(missing_orch)}",
                    "Run: bash install-orch-crons.sh --force")
        elif is_orch and not missing_orch:
            res.add("Orch crons", "PASS",
                    f"all {len(orch_crons)} orchestrator crons present (host: {hostname})")
        elif not is_orch and not missing_orch:
            # Worker agent that somehow has orch crons — warn
            res.add("Orch crons", "INFO",
                    f"orchestrator crons exist on non-orch host '{hostname}' (ok if backup)")
        # If not is_orch and missing_orch: expected — worker agents skip orch crons, no report needed

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
    """5. System resources: disk, memory, systemd service scope."""
    # ── Systemd service scope check (Linux only) ──
    if IS_LINUX:
        out = run_bg(["sh", "-c", "ls /etc/systemd/system/hermes-*.service 2>/dev/null"], timeout=5)
        if out.strip():
            count = len(out.strip().split("\n"))
            res.add("Systemd scope", "WARN",
                    f"{count} Hermes service(s) found in /etc/systemd/system/ (must use ~/.config/systemd/user/)",
                    "sudo systemctl disable --now hermes-dashboard hermes-health hermes-inbox hermes-gateway ; "
                    "sudo rm /etc/systemd/system/hermes-*.service ; "
                    "sudo rm /etc/systemd/system/multi-user.target.wants/hermes-*.service ; "
                    "sudo systemctl daemon-reload")
        else:
            res.add("Systemd scope", "PASS", "no system-level Hermes services (all user-level)")

    # ── Disk usage ──
    out = run_bg(["df", "-h", "/"], timeout=5)
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
    """6. Config consistency: env var cross-reference."""
    if not MODELS_ENV.exists():
        res.add("Config (.env)", "WARN", "Not found", "Create ~/hermes-cortex/.env with env vars")
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
        res.add("Config (.env)", "WARN", "File exists but no exports defined",
                 "Add JUDGE_MODEL, EMBEDDING_MODEL etc.")
        return

    consumers_by_var = find_script_consumers()
    for var, consumer_names in consumers_by_var.items():
        if var not in defined:
            res.add(f"Config ({var})", "WARN", f"Not defined in .env",
                     f"Add: export {var}=<model-name> to ~/hermes-cortex/.env")
        else:
            if consumer_names:
                res.add(f"Config ({var})", "PASS", f"defined, {len(consumer_names)} consumer(s) found")
            else:
                res.add(f"Config ({var})", "INFO", f"defined but zero consumer scripts reference it")


def check_nginx(res):
    """7. Nginx config: file exists, htpasswd, agent-card, SSL certs, syntax."""

    def _path_ok(p):
        """Check if a path exists, treating PermissionError as 'exists' (root-owned)."""
        try:
            return Path(p).exists()
        except PermissionError:
            return True  # file exists, just not readable by this user

    def _path_info(p):
        """Return readable status of a path, handling permission errors."""
        try:
            p_obj = Path(p)
            if p_obj.exists():
                return "exists"
            return "missing"
        except PermissionError:
            return "exists (root-owned, not readable by this user)"

    # ── OS-aware nginx paths ──
    nginx_brew_dir = None
    config_dir = None
    available_dir = None
    htpasswd_expected = None

    if IS_MAC:
        if os.uname().machine == "arm64":
            nginx_brew_dir = Path("/opt/homebrew/etc/nginx")
        else:
            nginx_brew_dir = Path("/usr/local/etc/nginx")
        config_dir = nginx_brew_dir / "servers"
        available_dir = config_dir
        htpasswd_expected = nginx_brew_dir / ".htpasswd"
    elif IS_LINUX:
        nginx_brew_dir = Path("/etc/nginx")
        config_dir = nginx_brew_dir / "sites-enabled"
        available_dir = nginx_brew_dir / "sites-available"
        htpasswd_expected = nginx_brew_dir / ".hermes-htpasswd"
    else:
        res.add("Nginx config", "INFO", "Unsupported OS — skipping nginx checks")
        return

    if not nginx_brew_dir or not nginx_brew_dir.is_dir():
        res.add("Nginx config", "INFO", "nginx not installed — skipping checks")
        return

    conf_available = available_dir / "hermes-services.conf"
    if not conf_available.is_file():
        res.add("Nginx config", "FAIL", f"not found at {conf_available}",
                "Run: sudo deploy/nginx/install-nginx-full.sh")
        return
    res.add("Nginx config", "PASS", f"found at {conf_available}")

    text = conf_available.read_text()

    # ── Check for unsubstituted placeholders ──
    placeholders = ["__HTPASSWD_FILE__", "__NGINX_CONFIG_DIR__", "__NGINX_LOG_DIR__",
                    "__CORTEX_HOME__", "__SSL_CERT__", "__SSL_CERT_KEY__"]
    found_placeholders = [p for p in placeholders if p in text]
    if found_placeholders:
        res.add("Nginx placeholders", "FAIL",
                f"unsubstituted: {', '.join(found_placeholders)}",
                "Run: cortex-update.sh --force-all or hermes-services-apply.py")

    # ── Verify htpasswd file ──
    htpasswd_path = None
    for line in text.split("\n"):
        m = re.search(r'auth_basic_user_file\s+(\S+?);?\s*$', line)
        if m:
            htpasswd_path = m.group(1).rstrip(";")
            break

    if htpasswd_path:
        p = Path(htpasswd_path)
        if _path_ok(htpasswd_path):
            res.add("Nginx htpasswd", "PASS", f"{htpasswd_path} {_path_info(htpasswd_path)}")
        elif _path_ok(str(htpasswd_expected)):
            res.add("Nginx htpasswd", "FAIL",
                    f"config points to '{htpasswd_path}' (not found) — expected '{htpasswd_expected}'",
                    f"Re-deploy: cortex-update.sh --force-all")
        else:
            res.add("Nginx htpasswd", "FAIL",
                    f"not found at '{htpasswd_path}' (and expected '{htpasswd_expected}' also missing)",
                    "Run: sudo htpasswd -c /etc/nginx/.hermes-htpasswd <user>")
    else:
        res.add("Nginx htpasswd", "INFO", "no auth_basic_user_file in config")

    # ── Verify agent-card paths ──
    seen_cards = set()
    agent_card_found = 0
    agent_card_missing = 0
    for line in text.split("\n"):
        m = re.search(r'alias\s+(\S+?/agent-card\.json)', line)
        if m:
            card_path = m.group(1).rstrip(";")
            if card_path in seen_cards:
                continue
            seen_cards.add(card_path)
            if _path_ok(card_path):
                agent_card_found += 1
            else:
                agent_card_missing += 1
                res.add("Nginx agent-card", "FAIL",
                        f"not found at '{card_path}'",
                        "Run: cortex-update.sh --force-all  OR  generate agent card in that directory")

    if agent_card_found > 0 and agent_card_missing == 0:
        res.add("Nginx agent-card", "PASS", f"{agent_card_found} agent card alias(es) resolve")

    # ── Verify SSL cert paths (deduplicated) ──
    seen_certs = set()
    cert_found = 0
    cert_missing = 0
    for line in text.split("\n"):
        m = re.search(r'ssl_certificate(?:_key)?\s+(\S+?);?\s*$', line)
        if m:
            raw = m.group(1).rstrip(";")
            if raw in seen_certs or "__SSL_CERT" in raw:
                continue
            seen_certs.add(raw)
            if _path_ok(raw):
                cert_found += 1
            else:
                cert_missing += 1
                label = "SSL cert" if "key" not in m.group(0) else "SSL key"
                res.add(f"Nginx {label}", "FAIL",
                        f"not found at '{raw}'",
                        "Renew cert: sudo certbot renew  OR  set CORTEX_SSL_CERT_PATH env var")

    if "__SSL_CERT__" not in text and cert_found > 0 and cert_missing == 0:
        res.add("Nginx SSL certs", "PASS", f"{len(seen_certs)} cert path(s) resolve")

    # ── nginx -t syntax check (with sudo for cert access) ──
    if nginx_available():
        if os.geteuid() == 0:
            out, code = run(["nginx", "-t"], timeout=10)
        elif run(["which", "sudo"], timeout=5)[0]:
            out, code = run(["sudo", "nginx", "-t"], timeout=15)
        else:
            res.add("Nginx syntax", "INFO", "not root and no sudo — skipping syntax check")
            return
        if code == 0:
            res.add("Nginx syntax", "PASS", "config valid (nginx -t)")
        else:
            lines = [l for l in out.split("\n") if "test failed" in l.lower() or "error" in l.lower()][:3]
            detail = "; ".join(lines) if lines else "syntax error"
            res.add("Nginx syntax", "FAIL", detail, "Check: sudo nginx -t")


def nginx_available():
    """Check if nginx binary is on PATH."""
    out, _ = run(["which", "nginx"], timeout=5)
    return bool(out.strip())


def check_governance(res):
    """7. Governance system: plugin, pre-commit hook, MCP servers, lock files, score-cycle."""
    config_text = read_file(CONFIG_FILE)
    state_dir = CORTEX_HOME / "state"
    hooks_dir = CORTEX_HOME / "hooks"
    global_hooks_path = run_bg(["git", "config", "--global", "core.hooksPath"], timeout=5)

    # ── Governance plugin ────────────────────────────────────
    plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
    plugin_src = CORTEX_REPO / "plugins" / "governance-enforcer"
    plugin_enabled = "governance-enforcer" in config_text and "enabled" in config_text

    if plugin_dir.exists() and (plugin_dir / "__init__.py").exists():
        res.add("Governance plugin", "PASS", "installed at ~/.hermes/plugins/governance-enforcer")
        if plugin_dir.is_symlink():
            target = os.readlink(str(plugin_dir))
            if plugin_src.exists() and str(plugin_src) in target:
                res.add("Plugin symlink", "PASS", f"symlinked to {target}")
            else:
                res.add("Plugin symlink", "WARN", f"symlinked to {target} (not ~/hermes-cortex/.hermes-cortex/...)",
                         "Re-create: ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/")
    else:
        res.add("Governance plugin", "FAIL", "not installed",
                 "Install: ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/\n"
                 "Then: hermes plugins enable governance-enforcer --allow-tool-override\n"
                 "Then: /reset (new session)")

    if plugin_enabled:
        res.add("Plugin config", "PASS", "enabled in config.yaml")
    else:
        res.add("Plugin config", "FAIL" if plugin_dir.exists() else "WARN",
                 "not enabled in config.yaml",
                 "Run: hermes plugins enable governance-enforcer --allow-tool-override")

    # Plugin source integrity
    if plugin_src.exists() and (plugin_src / "__init__.py").exists():
        res.add("Plugin source", "PASS", "source in repo at plugins/governance-enforcer")
    else:
        res.add("Plugin source", "FAIL", "source missing in repo",
                 "Check: ~/hermes-cortex/plugins/governance-enforcer/")

    # ── MCP servers ──────────────────────────────────────────
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if name not in config_text:
            res.add(f"MCP server ({name})", "FAIL", "not configured",
                     f"Run: hermes mcp add {name} --command ~/.hermes/hermes-agent/venv/bin/python3 "
                     f"--args ~/hermes-cortex/src/mcp-servers/{server_script}")
            continue

        res.add(f"MCP server ({name})", "PASS", "configured in config.yaml")

        # Check if MCP uses venv Python (not bare python3)
        if name == "loop-governance":
            # Try to find the command in config.yaml for this server
            cmd_match = re.search(
                rf'{re.escape(name)}.*?command:\s*(\S+)',
                config_text, re.DOTALL
            )
            if cmd_match:
                cmd = cmd_match.group(1)
                if "venv" in cmd and "python3" in cmd:
                    res.add(f"MCP Python ({name})", "PASS", f"uses venv: {cmd}")
                elif "python3" in cmd:
                    venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
                    if venv_python.exists():
                        res.add(f"MCP Python ({name})", "WARN",
                                 f"uses bare python3 (expected venv)",
                                 f"Run: hermes mcp update {name} --command {venv_python}")
                    else:
                        res.add(f"MCP Python ({name})", "WARN",
                                 f"uses python3 but venv not found at {venv_python}")


    # ── Pre-commit hook (global hooksPath) ────────────────────
    expected_hook_path = hooks_dir / "pre-commit"
    expected_hooks_path = str(hooks_dir)

    if global_hooks_path.rstrip("/") == expected_hooks_path:
        res.add("Global hooksPath", "PASS", f"core.hooksPath → {expected_hooks_path}")
    elif global_hooks_path:
        res.add("Global hooksPath", "WARN",
                 f"set to '{global_hooks_path}' (expected '{expected_hooks_path}')",
                 f"Run: git config --global core.hooksPath {expected_hooks_path}")
    else:
        res.add("Global hooksPath", "FAIL", "not set",
                 f"Run: git config --global core.hooksPath {expected_hooks_path}")

    if expected_hook_path.exists():
        content = expected_hook_path.read_text()
        if "score-cycle" in content and "governance" in content:
            res.add("Pre-commit hook", "PASS", "installed with governance check")
        else:
            res.add("Pre-commit hook", "WARN", "installed but may be outdated",
                     "Run: cp ~/hermes-cortex/src/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit")
    else:
        res.add("Pre-commit hook", "FAIL", f"not found at {expected_hook_path}",
                 "Install: cp ~/hermes-cortex/src/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit\n"
                 "Then: chmod +x ~/.hermes-cortex/hooks/pre-commit")

    # ── Pre-push hook (global) ────────────────────────────────
    expected_push_hook = hooks_dir / "pre-push"
    if expected_push_hook.exists():
        push_content = expected_push_hook.read_text()
        if "pre-push-pull" in push_content:
            res.add("Pre-push hook", "PASS", "installed with pull-before-push check")
        else:
            res.add("Pre-push hook", "WARN", "installed but may be outdated")
    else:
        res.add("Pre-push hook", "WARN", "not installed",
                 "Install: cp ~/hermes-cortex/src/scripts/pre-push-pull ~/.hermes-cortex/hooks/pre-push\n"
                 "Then: chmod +x ~/.hermes-cortex/hooks/pre-push")

    # ── Score-cycle CLI ───────────────────────────────────────
    score_paths = [
        HOME / ".local" / "bin" / "score-cycle",
        Path("/usr/local/bin/score-cycle"),
        CORTEX_HOME / "scripts" / "score-cycle",
    ]
    found_score = None
    for p in score_paths:
        if p.exists():
            found_score = p
            break
    if found_score:
        if found_score.is_symlink():
            target = os.readlink(str(found_score))
            if Path(target).exists():
                res.add("Score-cycle", "PASS", f"available at {found_score} → {target}")
            else:
                res.add("Score-cycle", "WARN", f"symlink broken: {found_score} → {target}",
                         "Re-run: bash ~/hermes-cortex/src/loop-governance/setup.sh")
        else:
            res.add("Score-cycle", "PASS", f"available at {found_score}")
    else:
        res.add("Score-cycle", "WARN", "not found in PATH",
                 "Run: bash ~/hermes-cortex/src/loop-governance/setup.sh to deploy scoring tools")

    # ── Stale governance locks (per-repo pattern) ──────────────
    if not state_dir.exists():
        res.add("State directory", "INFO", "does not exist (will be created on first begin_change)")
    else:
        lock_files = list(state_dir.glob(".governance-*.json"))
        if lock_files:
            stale_count = 0
            now = time.time()
            for lf in lock_files:
                try:
                    lock_data = json.loads(lf.read_text())
                    started = lock_data.get("started_at", "")
                    # Check if lock is older than 24 hours
                    if started:
                        try:
                            started_ts = datetime.fromisoformat(started).timestamp()
                            age_hours = (now - started_ts) / 3600
                            if age_hours > 24:
                                stale_count += 1
                                res.add(f"Stale lock ({lf.name})", "WARN",
                                         f"from {started} ({age_hours:.0f}h old)",
                                         f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                        except (ValueError, TypeError):
                            stale_count += 1
                            res.add(f"Stale lock ({lf.name})", "WARN",
                                     f"unparseable timestamp: {started}",
                                     f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                    else:
                        stale_count += 1
                        res.add(f"Stale lock ({lf.name})", "WARN",
                                 "no started_at field",
                                 f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")
                except (json.JSONDecodeError, OSError):
                    stale_count += 1
                    res.add(f"Stale lock ({lf.name})", "WARN",
                             "unparseable lock file",
                             f"Remove: rm -f ~/.hermes-cortex/state/{lf.name}")

            if stale_count == 0:
                res.add("Governance locks", "PASS",
                         f"{len(lock_files)} active lock(s), none stale")
        else:
            res.add("Governance locks", "PASS", "no lock files")


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

    # Fix: MCP server not configured (use venv Python)
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if f"MCP server ({name})" in fix_map and fix_map[f"MCP server ({name})"] == "FAIL":
            if CONFIG_FILE.exists() and CORTEX_REPO.exists():
                mcp_path = MCP_SERVERS_DIR / server_script
                venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
                if mcp_path.exists() and venv_python.exists():
                    if _run_fix(f"Adding MCP server {name} to config.yaml (venv Python)",
                                ["python3", "-c", f"""
import yaml, sys
with open('{CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
if 'mcpServers' not in cfg:
    cfg['mcpServers'] = {{}}
cfg['mcpServers']['{name}'] = {{
    'command': '{venv_python}',
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

    # Fix: MCP server uses bare python3 instead of venv
    for name in EXPECTED_MCP_SERVERS:
        if f"MCP Python ({name})" in fix_map and fix_map[f"MCP Python ({name})"] == "WARN":
            venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
            if venv_python.exists():
                if _run_fix(f"Updating MCP {name} to use venv Python",
                            ["hermes", "mcp", "update", name,
                             "--command", str(venv_python)]):
                    fixed += 1
                else:
                    failed += 1

    # Fix: governance plugin not installed/symlinked
    if "Governance plugin" in fix_map and fix_map["Governance plugin"] == "FAIL":
        plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
        plugin_src = CORTEX_REPO / ".hermes-cortex" / "plugins" / "governance-enforcer"
        if plugin_src.exists():
            if _run_fix("Symlinking governance plugin",
                        ["ln", "-sf", str(plugin_src), str(plugin_dir)]):
                fixed += 1
            else:
                failed += 1
        # Also try to enable it
        if _run_fix("Enabling governance plugin",
                    ["hermes", "plugins", "enable", "governance-enforcer", "--allow-tool-override"]):
            fixed += 1
        else:
            failed += 1

    # Fix: pre-commit hook not installed (global hooksPath)
    if "Pre-commit hook" in fix_map and "FAIL" in fix_map.get("Pre-commit hook", ""):
        hook_src = CORTEX_REPO / "src" / "scripts" / "pre-commit-score"
        hook_dest = CORTEX_HOME / "hooks" / "pre-commit"
        if hook_src.exists():
            if _run_fix("Installing pre-commit hook to shared hooks dir",
                        ["cp", str(hook_src), str(hook_dest)]):
                if _run_fix("Setting hook as executable",
                            ["chmod", "+x", str(hook_dest)]):
                    fixed += 1
                else:
                    failed += 1
            else:
                failed += 1

    # Fix: global hooksPath not set correctly
    if "Global hooksPath" in fix_map and fix_map.get("Global hooksPath") in ("FAIL", "WARN"):
        expected_hooks_path = str(CORTEX_HOME / "hooks")
        if _run_fix("Setting global hooksPath",
                    ["git", "config", "--global", "core.hooksPath", expected_hooks_path]):
            fixed += 1
        else:
            failed += 1

    # Fix: pre-push hook not installed
    if "Pre-push hook" in fix_map and "not installed" in fix_map.get("Pre-push hook", ""):
        push_src = CORTEX_REPO / "src" / "scripts" / "pre-push-pull"
        push_dest = CORTEX_HOME / "hooks" / "pre-push"
        if push_src.exists():
            if _run_fix("Installing pre-push hook",
                        ["cp", str(push_src), str(push_dest)]):
                if _run_fix("Setting hook as executable",
                            ["chmod", "+x", str(push_dest)]):
                    fixed += 1
                else:
                    failed += 1
            else:
                failed += 1

    # Fix: stale governance locks (per-repo pattern)
    state_dir = CORTEX_HOME / "state"
    if state_dir.exists():
        for lf in state_dir.glob(".governance-*.json"):
            try:
                lock_data = json.loads(lf.read_text())
                started = lock_data.get("started_at", "")
                if started:
                    try:
                        started_ts = datetime.fromisoformat(started).timestamp()
                        age_hours = (time.time() - started_ts) / 3600
                        if age_hours > 24:
                            lf.unlink()
                            print(f"  → Removing stale lock: {lf.name} ({age_hours:.0f}h old)")
                            print(f"  ✅ Done")
                            fixed += 1
                    except (ValueError, TypeError):
                        lf.unlink()
                        print(f"  → Removing unparseable lock: {lf.name}")
                        print(f"  ✅ Done")
                        fixed += 1
                else:
                    lf.unlink()
                    print(f"  → Removing lock with no timestamp: {lf.name}")
                    print(f"  ✅ Done")
                    fixed += 1
            except (json.JSONDecodeError, OSError):
                lf.unlink()
                print(f"  → Removing corrupt lock: {lf.name}")
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
                   check_system, check_config, check_nginx, check_governance, check_install]

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
