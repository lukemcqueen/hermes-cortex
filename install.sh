#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Full System Installer
#  https://github.com/lukemcqueen/hermes-cortex
#
#  Installs: Ollama · Bun · gbrain · Langfuse† · Cortex Dashboard† ·
#            nginx† · Brain directory structure · Hermes plugins ·
#            Web Cache · Offline Knowledge (kiwix ZIM) · Skills
#  † Server profile only (CORTEX_PROFILE=server). Laptop profile
#    (CORTEX_PROFILE=laptop) skips Docker-dependent services.
#
#  Platforms: macOS (native) · Linux (systemd) · Windows (scheduled tasks)
#  Set CORTEX_OS to override auto-detection: darwin, linux, windows
#  Launchd services · Cron jobs (via agent)
#
#  Idempotent — safe to re-run. Skips already-installed steps.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
IFS=$'\n\t'
VERSION="1.0.0"

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'
STEP=0

info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }
header() {
  printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"
}
step() {
  STEP=$((STEP+1))
  printf "\n${MAGENTA}${BOLD}[%s/%s]${RESET} ${BOLD}%s${RESET}\n" "$STEP" "${TOTAL_STEPS:-10}" "$1"
}
ok()   { printf "  ${GREEN}done${RESET}\n"; }
skip() { printf "  ${YELLOW}skip${RESET} — %s\n" "$1"; }

# ── Abort handler ───────────────────────────────────────────
trap 'printf "\n${RED}Installation aborted at step $STEP${RESET}\n"' EXIT

# ── Source OS Abstraction Layer ─────────────────────────────
source "${SCRIPT_DIR}/scripts/os-config.sh"
source "${SCRIPT_DIR}/scripts/service-writer.sh"

# ─────────────────────────────────────────────────────────────
#  0. System Verification Check
# ─────────────────────────────────────────────────────────────
header "SYSTEM VERIFICATION"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
CHECK_SCRIPT="${SCRIPT_DIR}/check-system.sh"

if [[ -f "$CHECK_SCRIPT" ]]; then
  bash "$CHECK_SCRIPT" || {
    error "System verification failed. Review the issues above."
    error "Fix them and re-run install.sh"
    exit 1
  }
  printf "\n"
else
  warn "check-system.sh not found — skipping verification"
  printf "\n"
fi

# ─────────────────────────────────────────────────────────────
#  Prerequisites & Configuration
# ─────────────────────────────────────────────────────────────
header "PREREQUISITES"

# OS-specific notes
if [[ "$CORTEX_OS" == "macos" ]]; then
  :  # Native — full support
elif [[ "$CORTEX_OS" == "linux" ]]; then
  warn "Linux detected — using systemd services. Some macOS-specific paths adjusted."
elif [[ "$CORTEX_OS" == "windows" ]]; then
  warn "Windows detected — using scheduled tasks. Some features (Dashboard, nginx) limited."
fi
info "Profile: ${CORTEX_PROFILE}"
if [[ "$CORTEX_PROFILE" == "laptop" ]]; then
  info "  Laptop mode: skipping nginx, Langfuse, Dashboard (Docker not required)"
fi

# User info
CORTEX_USER="${CORTEX_USER:-$USER}"
CORTEX_HOME="${CORTEX_HOME:-$HOME}"
BRAIN_DIR="${CORTEX_HOME}/brain"
HERMES_HOME="${HERMES_HOME:-${CORTEX_HOME}/.hermes}"

# Detect script directory
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# Brain sources — default is 'default' + optionally more
if [[ -z "${CORTEX_SOURCES:-}" ]]; then
  # Single-user default
  CORTEX_SOURCES="default"
  info "Brain sources: ${CORTEX_SOURCES}"
  info "  To add more sources (e.g. for multi-person), set CORTEX_SOURCES before running:"
  info "    export CORTEX_SOURCES='luke,amy,shared,default'"
fi

IFS=',' read -ra SOURCES <<< "$CORTEX_SOURCES"
TOTAL_STEPS=22
STEP=0

# Ensure Hermes is installed
if ! command -v hermes &>/dev/null && [[ ! -x "${HERMES_HOME}/hermes-agent/venv/bin/hermes" ]]; then
  warn "Hermes Agent not found. Install it first: https://hermes-agent.nousresearch.com/docs"
  warn "The script will install everything else, but you'll need Hermes for the final agent-side setup."
fi

# Ensure package manager
if [[ "$CORTEX_OS" == "macos" ]] && ! command -v brew &>/dev/null; then
  step "Installing Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ "$(uname -m)" == "arm64" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  ok
fi

# ─────────────────────────────────────────────────────────────
#  1. Ollama — local LLM server for embeddings
# ─────────────────────────────────────────────────────────────
step "Installing Ollama (local LLM server)"
bash "${SCRIPT_DIR}/scripts/install-ollama.sh" install
ok

# Configure Ollama service
step "Configuring Ollama service"
bash "${SCRIPT_DIR}/scripts/install-ollama.sh" service
ok

# Wait for Ollama to be ready
step "Waiting for Ollama to respond…"
bash "${SCRIPT_DIR}/scripts/install-ollama.sh" wait
ok

# Pull embedding model
step "Pulling embedding model (nomic-embed-text)"
bash "${SCRIPT_DIR}/scripts/install-ollama.sh" embed nomic-embed-text
ok

# ─────────────────────────────────────────────────────────────
#  2. Bun — JavaScript runtime for gbrain
# ─────────────────────────────────────────────────────────────
step "Installing Bun"
if command -v bun &>/dev/null || [[ -x "${CORTEX_HOME}/.bun/bin/bun" ]]; then
  skip "already installed — $(bun --version 2>/dev/null || echo 'bun found')"
else
  curl -fsSL https://bun.sh/install | bash
  # Ensure bun is in PATH for subsequent steps
  export PATH="${CORTEX_HOME}/.bun/bin:$PATH"
  ok
fi

# Ensure bun is in PATH
if ! command -v bun &>/dev/null; then
  export PATH="${CORTEX_HOME}/.bun/bin:$PATH"
fi

# ─────────────────────────────────────────────────────────────
#  3. gbrain — Knowledge Brain
# ─────────────────────────────────────────────────────────────
step "Installing gbrain (knowledge brain)"
if command -v gbrain &>/dev/null || [[ -x "${CORTEX_HOME}/.bun/bin/gbrain" ]]; then
  skip "already installed — $(gbrain --version 2>/dev/null || echo 'gbrain found')"
else
  # NOTE: plain 'gbrain' on npm is a different package (stormcolor GPU JS, no CLI).
  # garrytan/gbrain is the actual knowledge brain tool with 20k+ stars.
  bun install -g github:garrytan/gbrain
  ok
fi

# Ensure gbrain is callable
GBRAIN_CMD="${CORTEX_HOME}/.bun/bin/gbrain"
if ! command -v gbrain &>/dev/null; then
  alias gbrain="$GBRAIN_CMD" 2>/dev/null || true
fi

# Init gbrain (PGLite, local)
step "Initializing gbrain with PGLite (local, zero-config)"
if [[ -f "${CORTEX_HOME}/.gbrain/brain.pglite" ]]; then
  skip "brain already exists"
else
  "$GBRAIN_CMD" init --pglite --embedding-model ollama:nomic-embed-text --yes 2>/dev/null || \
    "$GBRAIN_CMD" init --pglite --embedding-model ollama:nomic-embed-text
  ok
fi

# Apply any pending migrations
step "Applying pending gbrain migrations"
if "$GBRAIN_CMD" doctor --json --fast 2>/dev/null | grep -q '"pending_count":0'; then
  skip "no pending migrations"
else
  "$GBRAIN_CMD" apply-migrations --yes 2>/dev/null || true
  ok
fi

# ─────────────────────────────────────────────────────────────
#  4. Brain Directory Structure
# ─────────────────────────────────────────────────────────────
step "Creating brain directory structure"

# Default MECE structure for each source
MECE_DIRS="archive civic companies concepts conversations deals hiring household ideas inbox media meetings org people personal programs projects prompts sources writing"

for source in "${SOURCES[@]}"; do
  source_dir="${BRAIN_DIR}/${source}"
  if [[ -d "$source_dir" ]]; then
    skip "${source} — already exists"
  else
    mkdir -p "$source_dir"
    for dir in $MECE_DIRS; do
      mkdir -p "${source_dir}/${dir}" 2>/dev/null || true
    done

    # Create index.md with schema docs
    if [[ ! -f "${source_dir}/index.md" ]]; then
      cat > "${source_dir}/index.md" <<INDEXEOF
# Brain Source: ${source}

## Schema

| Directory | Purpose |
|-----------|---------|
| archive/ | Old / resolved items |
| civic/ | Civic, community, volunteering |
| companies/ | Companies, vendors, orgs |
| concepts/ | Ideas, frameworks, mental models |
| conversations/ | Chat transcripts, meeting notes |
| deals/ | Deals, contracts, agreements |
| hiring/ | Hiring, candidates, interviews |
| household/ | Home, family, chores, logistics |
| ideas/ | Raw ideas, brainstorming |
| inbox/ | Capture zone — unprocessed notes |
| media/ | Books, articles, podcasts |
| meetings/ | Meeting notes, agendas |
| org/ | Organization structure, roles |
| people/ | People, contacts, relationships |
| personal/ | Personal notes, journal |
| programs/ | Programs, courses, training |
| projects/ | Active projects, tasks |
| prompts/ | Saved prompts, templates |
| sources/ | Reference material, links |
| writing/ | Long-form writing, drafts |

## Source Type

- **federated:** \`true\` → auto-searched on every query
- **federated:** \`false\` → searched only with \`--source ${source}\`

---

*Created by Hermes Cortex installer v${VERSION}*
INDEXEOF
    fi
    info "  Created ${source_dir}/"
  fi
done

# ─────────────────────────────────────────────────────────────
#  5. Brain .gitignore — Protect memory and secrets per source
# ─────────────────────────────────────────────────────────────
step "Adding .gitignore to brain sources"
GITIGNORE_TEMPLATE="${SCRIPT_DIR}/docs/templates/gitignore.brain"
GITIGNORE_SRC=""
if [[ -f "$GITIGNORE_TEMPLATE" ]]; then
  GITIGNORE_SRC="$GITIGNORE_TEMPLATE"
fi
for source in "${SOURCES[@]}"; do
  source_dir="${BRAIN_DIR}/${source}"
  if [[ ! -d "$source_dir" ]]; then
    continue
  fi
  if [[ -f "${source_dir}/.gitignore" ]]; then
    skip "${source} — .gitignore already exists"
  elif [[ -n "$GITIGNORE_SRC" ]]; then
    cp "$GITIGNORE_SRC" "${source_dir}/.gitignore"
    info "  Added .gitignore to ${source}/"
  else
    # Write inline fallback
    cat > "${source_dir}/.gitignore" <<GITEOF
# Hermes Cortex brain source — never commit per-instance memory or secrets
MEMORY.md
USER.md
.env
.env.*
*.pem
*.key
*.cert
.DS_Store
Thumbs.db
GITEOF
    info "  Created inline .gitignore for ${source}/"
  fi
done
ok

# ─────────────────────────────────────────────────────────────
#  6. gbrain Sources & Sync Daemon
# ─────────────────────────────────────────────────────────────
step "Configuring gbrain sources"

for source in "${SOURCES[@]}"; do
  source_dir="${BRAIN_DIR}/${source}"
  # The 'default' gbrain source is special (backs pre-v0.17 brain) and cannot be
  # removed or have --path set. Skip it here; non-default sources get --path.
  if [[ "${source}" == "default" ]]; then
    skip "'default' gbrain source is built-in (cannot set --path)"
    continue
  fi
  # Check if source already exists in gbrain
  if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "${source}"; then
    skip "gbrain source '${source}' already configured"
  else
    # Init git repo in source dir if not already
    if [[ ! -d "${source_dir}/.git" ]]; then
      git -C "${source_dir}" init 2>/dev/null || true
      git -C "${source_dir}" add -A 2>/dev/null || true
      git -C "${source_dir}" commit -m "initial brain state" 2>/dev/null || true
    fi
    "$GBRAIN_CMD" sources add "${source}" --path "${source_dir}" --name "${source}" 2>/dev/null || \
      warn "Failed to add source '${source}' — may need gbrain re-init"
    info "  Added gbrain source: ${source}"
  fi
done

# Federate 'shared' if it exists
if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "shared"; then
  "$GBRAIN_CMD" sources federate shared 2>/dev/null || true
  info "  Federated 'shared' source (auto-searched)"
fi

# Create gbrain sync daemon
step "Creating gbrain sync-watch daemon ($SERVICE_MANAGER)"
bash "${SCRIPT_DIR}/scripts/install-gbrain-sync.sh"
ok

# ─────────────────────────────────────────────────────────────
#  7. Hermes gbrain Plugin (/brain slash command)
# ─────────────────────────────────────────────────────────────
step "Installing gbrain Hermes plugin (/brain command)"

PLUGIN_DIR="${HERMES_HOME}/plugins/gbrain-command"
if [[ -f "${PLUGIN_DIR}/__init__.py" ]]; then
  skip "plugin already installed"
else
  mkdir -p "$PLUGIN_DIR"

  # plugin.yaml
  cat > "${PLUGIN_DIR}/plugin.yaml" <<YAMLEOF
name: gbrain-command
version: 1.1.0
description: "Query your gbrain knowledge brain. Usage: /brain [source] <query>"
author: ${CORTEX_USER}
hooks: []
YAMLEOF

  # Use python3 to generate __init__.py (avoids bash/Python ${…} conflicts in heredocs)
  python3 << 'PYSCRIPT'
import os, json, shlex

cortex_home = os.environ.get('CORTEX_HOME', os.path.expanduser('~'))
hermes_home = os.environ.get('HERMES_HOME', os.path.join(cortex_home, '.hermes'))
sources_str = os.environ.get('CORTEX_SOURCES', 'default')
sources = [s.strip() for s in sources_str.split(',') if s.strip()]

plugin_dir = os.path.join(hermes_home, 'plugins', 'gbrain-command')
os.makedirs(plugin_dir, exist_ok=True)

bun_path = os.path.join(cortex_home, '.bun/bin')
gbrain_bin = f'{bun_path}/bun {bun_path}/gbrain'

# Build sources dictionary
sources_dict = {}
for s in sources:
    sources_dict[s] = f'--source {s}'

default_sources_parts = [f'--source {s}' for s in sources if s != 'default']
default_source = ' '.join(default_sources_parts)

# Help text
help_parts = [f'  /brain {s} <query>          {s}\'s brain only\n' for s in sources if s != 'default']
source_help = ''.join(help_parts)

lines = []
lines.append('"""')
lines.append('gbrain slash command plugin for Hermes Agent.')
lines.append('')
lines.append('Provides /brain <query> — queries gbrain knowledge base.')
lines.append('Dynamically generated by hermes-cortex installer.')
lines.append('"""')
lines.append('')
lines.append('from __future__ import annotations')
lines.append('')
lines.append('import asyncio')
lines.append('import logging')
lines.append('import shlex')
lines.append('from typing import Optional')
lines.append('')
lines.append('logger = logging.getLogger(__name__)')
lines.append('')
lines.append(f'_GBRAIN_BIN = {shlex.quote(gbrain_bin)}')
lines.append('')
lines.append('# Source presets')
lines.append('_SOURCES = {')
for s in sources:
    lines.append(f'    {shlex.quote(s)}: {shlex.quote(f"--source {s}")},')
lines.append('}')
lines.append('')
lines.append('_DESCRIPTIONS = {')
for s in sources:
    lines.append(f'    {shlex.quote(s)}: {shlex.quote(f"{s}\'s brain")},')
lines.append('}')
lines.append('')
lines.append(f'_DEFAULT_SOURCE = {shlex.quote(default_source)}')
lines.append('')
help_text = f"""/brain — Search your gbrain knowledge base

**Usage:**
  /brain <query>               All sources (default)
{source_help}
**Examples:**
  /brain what's on my mind?
  /brain --help                Show this help

Results from local gbrain (PGLite) at ~/.gbrain/brain.pglite.
"""
lines.append('_HELP_TEXT = ' + repr(help_text))
lines.append('')
lines.append('')
lines.append('async def _run_gbrain_query(query: str, source_flags: str) -> str:')
lines.append('    """Run gbrain query and return formatted results."""')
lines.append('    cmd = f"{_GBRAIN_BIN} query {source_flags} {shlex.quote(query)} 2>&1 | head -40"')
lines.append('    logger.debug("Running gbrain query: %s", cmd)')
lines.append('')
lines.append('    proc = await asyncio.create_subprocess_shell(')
lines.append('        cmd,')
lines.append('        stdout=asyncio.subprocess.PIPE,')
lines.append('        stderr=asyncio.subprocess.PIPE,')
lines.append('    )')
lines.append('')
lines.append('    try:')
lines.append('        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)')
lines.append('    except asyncio.TimeoutError:')
lines.append('        proc.kill()')
lines.append('        return "\u23f1\ufe0f Brain query timed out after 30s."')
lines.append('')
lines.append('    output = (stdout.decode("utf-8", errors="replace") or "").strip()')
lines.append('    err = (stderr.decode("utf-8", errors="replace") or "").strip()')
lines.append('')
lines.append('    if proc.returncode != 0:')
lines.append('        return f"\u274c Brain query failed (exit {proc.returncode}):\\\n{err or output}"')
lines.append('')
lines.append('    if not output:')
lines.append('        return "\U0001f914 No results found in your brain."')
lines.append('')
lines.append('    # Format nicely')
lines.append('    lines = output.split("\\n")')
lines.append('    clean_lines = [l for l in lines if not l.startswith("[") and not l.startswith("  ")]')
lines.append('    if not clean_lines:')
lines.append('        clean_lines = lines')
lines.append('    formatted = "\\n".join(clean_lines[:30])')
lines.append('')
lines.append('    return f"\U0001f9e0 **Results:**\\n\\n{formatted}"')
lines.append('')
lines.append('')
lines.append('def _run_gbrain_query_sync(query: str, source_flags: str) -> str:')
lines.append('    try:')
lines.append('        return asyncio.run(_run_gbrain_query(query, source_flags))')
lines.append('    except RuntimeError:')
lines.append('        loop = asyncio.new_event_loop()')
lines.append('        try:')
lines.append('            return loop.run_until_complete(_run_gbrain_query(query, source_flags))')
lines.append('        finally:')
lines.append('            loop.close()')
lines.append('')
lines.append('')
lines.append('def _parse_source(args: str) -> tuple[str, str]:')
lines.append('    """Parse source prefix from args. Returns (query, source_flags)."""')
lines.append('    for source_key in _SOURCES:')
lines.append('        if args.lower().startswith(f"{source_key} "):')
lines.append('            query = args[len(source_key):].strip()')
lines.append('            return query, _SOURCES[source_key]')
lines.append('')
lines.append('    return args, _DEFAULT_SOURCE')
lines.append('')
lines.append('')
lines.append('def _handle_slash(raw_args: str) -> Optional[str]:')
lines.append('    """Handle /brain command."""')
lines.append('    args = raw_args.strip()')
lines.append('')
lines.append('    if not args or args in {"--help", "-h", "help"}:')
lines.append('        return _HELP_TEXT')
lines.append('')
lines.append('    query, source_flags = _parse_source(args)')
lines.append('')
lines.append('    if not query:')
lines.append('        return "Please provide a query. Usage: `/brain <query>`"')
lines.append('')
lines.append('    return _run_gbrain_query_sync(query, source_flags)')
lines.append('')
lines.append('')
lines.append('def register(ctx) -> None:')
lines.append('    """Register /brain slash command."""')
lines.append('    ctx.register_command(')
lines.append('        "brain",')
lines.append('        handler=_handle_slash,')
lines.append('        description="Query your gbrain ([source] <query>)",')
lines.append('        args_hint="[source] <query>",')
lines.append('    )')
lines.append('    logger.info("Registered /brain slash command \u2014 Hermes Cortex")')

with open(os.path.join(plugin_dir, '__init__.py'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'  Wrote {len(lines)} lines to {plugin_dir}/__init__.py')
PYSCRIPT
  ok
  info "Plugin written to ${PLUGIN_DIR}/"
  info "  Run /reset or /new in Hermes to activate"
  ok
fi

# ─────────────────────────────────────────────────────────────
#  8. Hermes Scripts (heartbeat, memory-to-brain)
# ─────────────────────────────────────────────────────────────
step "Installing Hermes utility scripts"

SCRIPTS_DIR="${HERMES_HOME}/scripts"
mkdir -p "$SCRIPTS_DIR"

# ── heartbeat.py ──────────────────────────────────────────
HEARTBEAT_PATH="${SCRIPTS_DIR}/heartbeat.py"
if [[ -f "$HEARTBEAT_PATH" ]]; then
  skip "heartbeat.py already exists"
else
  cat > "$HEARTBEAT_PATH" <<'HEARTBEAT'
#!/usr/bin/env python3
"""heartbeat.py — System health watchdog for Hermes/gbrain stack.

Checks critical daemons and services:
  - Ollama (LLM server)
  - gbrain sync daemon
  - Hermes gateway
  - Memory-to-brain sync freshness
  - Disk space

Outputs a concise health report. Designed for cron integration:
  - Non-empty stdout on FAILURE → cron delivers alert
  - Empty stdout when healthy → silent (watchdog pattern)
"""
import json, os, subprocess, sys, re
from datetime import datetime, timedelta
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
NOW = datetime.now()


def check_launchd(job_label):
    try:
        result = subprocess.run(["launchctl", "list", job_label],
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"status": "DOWN", "detail": f"launchctl list failed: {result.stderr.strip()}"}
        stdout = result.stdout.strip()
        pid_match = re.search(r'"PID"\s*=\s*(\d+);', stdout)
        exit_match = re.search(r'"LastExitStatus"\s*=\s*(\d+);', stdout)
        if pid_match:
            pid = pid_match.group(1)
            exit_code = int(exit_match.group(1)) if exit_match else 0
            if exit_code != 0:
                return {"status": "DEGRADED", "detail": f"Running (PID {pid}) but last exit was {exit_code}"}
            return {"status": "UP", "detail": f"PID {pid}"}
        parts = stdout.split("\t")
        if len(parts) >= 2:
            pid, exit_code = parts[0], parts[1]
            if pid == "-":
                return {"status": "DOWN", "detail": f"No PID (exit code: {exit_code})"}
            return {"status": "UP", "detail": f"PID {pid}"}
        return {"status": "ERROR", "detail": f"Unrecognized output: {stdout[:200]}"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def check_gateway_log():
    log_dir = HERMES_HOME / "logs"
    if not log_dir.exists():
        return {"status": "UNKNOWN", "detail": "No log directory"}
    recent = any(
        (NOW - datetime.fromtimestamp(f.stat().st_mtime)) < timedelta(minutes=30)
        for f in log_dir.glob("*.log*")
    )
    if recent:
        return {"status": "UP", "detail": "Activity in last 30 min"}
    return {"status": "DEGRADED", "detail": "No log activity in 30+ min"}


def check_disk_usage(path="/"):
    try:
        result = subprocess.run(["df", "-h", path], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            pct_str = lines[1].split()[4].rstrip("%")
            pct = int(pct_str)
            status = "UP" if pct < 85 else "DEGRADED" if pct < 95 else "DOWN"
            return {"status": status, "detail": f"{pct}% used on {path}"}
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}


def run():
    checks = {
        "Ollama": check_launchd("com.ollama.serve"),
        "gbrain sync daemon": check_launchd("com.gbrain.sync-watch"),
        "Gateway activity": check_gateway_log(),
        "Disk usage": check_disk_usage(),
    }
    status_counts = {}
    for name, result in checks.items():
        s = result["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    overall = "HEALTHY"
    if status_counts.get("DOWN", 0) > 0:
        overall = "CRITICAL"
    elif status_counts.get("ERROR", 0) > 0:
        overall = "ERROR"
    elif status_counts.get("DEGRADED", 0) > 0:
        overall = "DEGRADED"

    now_str = NOW.strftime("%Y-%m-%d %H:%M:%S %Z")
    report = f"📡 Hermes Heartbeat — {now_str}\nOverall: {overall}\n\n"
    icons = {"UP": "✅", "DEGRADED": "⚠️", "DOWN": "❌", "ERROR": "🔴", "UNKNOWN": "❓"}
    for name, result in checks.items():
        report += f"{icons.get(result['status'], '❓')} {name}: {result['status']} — {result['detail']}\n"

    if overall == "HEALTHY" and "--report" not in sys.argv:
        return ""
    return report


if __name__ == "__main__":
    output = run()
    if output:
        print(output)
HEARTBEAT
  chmod +x "$HEARTBEAT_PATH"
  ok
fi

# ── memory-to-brain.py ─────────────────────────────────────
M2B_PATH="${SCRIPTS_DIR}/memory-to-brain.py"
if [[ -f "$M2B_PATH" ]]; then
  skip "memory-to-brain.py already exists"
else
  cat > "$M2B_PATH" <<'M2BPY'
#!/usr/bin/env python3
"""memory-to-brain.py — Sync Hermes agent memory → gbrain (long-term brain)

Reads MEMORY.md and USER.md from the active Hermes profile,
formats them as searchable gbrain pages under ~/brain/shared/hermes-memory/,
then writes them for the gbrain sync daemon to pick up.
"""
import os, subprocess, sys
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
MEMORY_DIR = HERMES_HOME / "memories"
OUT_DIR = BRAIN_SHARED / "hermes-memory"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
ENTRY_DELIMITER = "\n§\n"


def read_entries(filepath):
    if not filepath.exists() or filepath.stat().st_size == 0:
        return []
    text = filepath.read_text(encoding="utf-8")
    return [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]


def build_page_content(entries, source_label, color):
    lines = [
        f"# Hermes Memory — {source_label}",
        f"Last synced: {TIMESTAMP}",
        f"",
        f"## Entries",
        f"",
    ]
    for i, entry in enumerate(entries, 1):
        lines.append(f"### {i}. {entry.split(chr(10))[0][:80]}")
        lines.append(entry.strip())
        lines.append("")
    return "\n".join(lines)


def write_page(slug, content):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / slug
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def git_commit(path, message):
    try:
        subprocess.run(["git", "-C", str(path), "add", "."],
                       capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(path), "commit", "--allow-empty",
                        "-m", message],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    memory_file = MEMORY_DIR / "memory.txt"
    user_file = MEMORY_DIR / "user.txt"

    memory_entries = read_entries(memory_file)
    user_entries = read_entries(user_file)

    changed = 0

    if memory_entries:
        content = build_page_content(memory_entries, "MEMORY.md", "blue")
        if write_page("hermes-memory.md", content):
            changed += 1
            print(f"  Updated hermes-memory.md ({len(memory_entries)} entries)")

    if user_entries:
        content = build_page_content(user_entries, "USER.md", "green")
        if write_page("hermes-user.md", content):
            changed += 1
            print(f"  Updated hermes-user.md ({len(user_entries)} entries)")

    git_commit(BRAIN_SHARED, f"hermes-memory sync: {TIMESTAMP}")

    if changed:
        print(f"✓ Synced {changed} page(s) to {OUT_DIR}")
    else:
        print("No changes — memory already up to date")


if __name__ == "__main__":
    main()
M2BPY
  chmod +x "$M2B_PATH"
  ok
fi

# ─────────────────────────────────────────────────────────────
#  9. Seed Memory Files — Bootstrapping templates
# ─────────────────────────────────────────────────────────────
step "Seeding initial memory files (MEMORY.md, USER.md)"

# Find the template seed files
SEED_MEMORY="${SCRIPT_DIR}/docs/templates/MEMORY.seed.md"
SEED_USER="${SCRIPT_DIR}/docs/templates/USER.seed.md"
HERMES_MEMORIES="${HERMES_HOME}/memories"

# Create memory directory if it doesn't exist
mkdir -p "$HERMES_MEMORIES"

# Copy seed files only if they don't already exist (don't overwrite)
if [[ -f "$SEED_MEMORY" ]] && [[ ! -f "${HERMES_MEMORIES}/MEMORY.md" ]]; then
  cp "$SEED_MEMORY" "${HERMES_MEMORIES}/MEMORY.md"
  info "  Created MEMORY.md from seed template"
else
  skip "MEMORY.md already exists or template not found"
fi

if [[ -f "$SEED_USER" ]] && [[ ! -f "${HERMES_MEMORIES}/USER.md" ]]; then
  cp "$SEED_USER" "${HERMES_MEMORIES}/USER.md"
  info "  Created USER.md from seed template"
else
  skip "USER.md already exists or template not found"
fi

# Create an empty .gitkeep so the directory is clean (not git-tracked anyway)
touch "$HERMES_MEMORIES/.gitkeep"
ok

# ─────────────────────────────────────────────────────────────
#  10. Install Hermes Skills — Shared skills from the repo
# ─────────────────────────────────────────────────────────────
step "Installing Hermes skills from repo"
SKILLS_REPO="${SCRIPT_DIR}/skills"
HERMES_SKILLS="${HERMES_HOME}/skills"
if [[ -d "$SKILLS_REPO" ]]; then
  count=0
  while IFS= read -r -d '' skill_file; do
    # Compute destination path relative to skills/ dir
    rel_path="${skill_file#$SKILLS_REPO/}"
    dest="${HERMES_SKILLS}/${rel_path}"
    dest_dir="$(dirname "$dest")"
    if [[ ! -f "$dest" ]]; then
      mkdir -p "$dest_dir"
      cp "$skill_file" "$dest"
      count=$((count + 1))
    fi
  done < <(find "$SKILLS_REPO" -name "SKILL.md" -type f -print0)
  # Also copy reference files
  while IFS= read -r -d '' ref_file; do
    rel_path="${ref_file#$SKILLS_REPO/}"
    dest="${HERMES_SKILLS}/${rel_path}"
    dest_dir="$(dirname "$dest")"
    if [[ ! -f "$dest" ]]; then
      mkdir -p "$dest_dir"
      cp "$ref_file" "$dest"
    fi
  done < <(find "$SKILLS_REPO" -path "*/references/*" -type f -print0)
  info "  Installed ${count} skills (skipped existing)"
else
  skip "no skills/ directory in repo"
fi
ok

# ─────────────────────────────────────────────────────────────
#  11. Web Cache — Local Semantic Web Cache
# ─────────────────────────────────────────────────────────────
step "Installing Web Cache (semantic web result cache)"
WEB_CACHE_REPO="${SCRIPT_DIR}/web-cache"
WEB_CACHE_DEST="${HERMES_HOME}/web-cache"
HERMES_BIN="${HERMES_HOME}/bin"
if [[ -d "$WEB_CACHE_REPO" ]]; then
  mkdir -p "$WEB_CACHE_DEST" "$HERMES_BIN"
  # Copy the Python tool
  cp "${WEB_CACHE_REPO}/web_cache.py" "$WEB_CACHE_DEST/"
  chmod +x "${WEB_CACHE_DEST}/web_cache.py"
  # Copy the wrapper script
  cp "${WEB_CACHE_REPO}/web_cache.sh" "$WEB_CACHE_DEST/"
  chmod +x "${WEB_CACHE_DEST}/web_cache.sh"
  # Create symlink in hermes bin directory
  ln -sf "${WEB_CACHE_DEST}/web_cache.sh" "${HERMES_BIN}/web_cache"
  info "  Installed web cache tool"
  # Create the venv if not exists
  if [[ ! -d "${WEB_CACHE_DEST}/.venv" ]]; then
    python3 -m venv "${WEB_CACHE_DEST}/.venv" 2>/dev/null
    "${WEB_CACHE_DEST}/.venv/bin/pip" install sqlite-vec requests 2>/dev/null && \
      info "  Created venv with sqlite-vec + requests"
  else
    skip "  venv already exists"
  fi
  # Initialize the cache DB
  "${WEB_CACHE_DEST}/.venv/bin/python3" "${WEB_CACHE_DEST}/web_cache.py" stats >/dev/null 2>&1 && \
    info "  Cache DB initialized"
else
  skip "no web-cache/ directory in repo"
fi
ok

# ─────────────────────────────────────────────────────────────
#  12. Langfuse — LLM Observability (Docker Compose)
# ─────────────────────────────────────────────────────────────
if [[ "$CORTEX_PROFILE" == "server" ]]; then
step "Installing Langfuse (LLM observability)"

LANGFUSE_DIR="${CORTEX_HOME}/langfuse"
LANGFUSE_COMPOSE="${CORTEX_HOME}/langfuse/docker-compose.yml"

if [[ -d "$LANGFUSE_DIR" ]] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "langfuse"; then
  skip "Langfuse already running"
else
  mkdir -p "$LANGFUSE_DIR"
  
  # Copy docker-compose from repo if not exists
  if [[ ! -f "$LANGFUSE_COMPOSE" ]]; then
    # Check if we're in the repo
    if [[ -f "${CORTEX_HOME}/Developer/AI/hermes-cortex/docker-compose.langfuse.yml" ]]; then
      cp "${CORTEX_HOME}/Developer/AI/hermes-cortex/docker-compose.langfuse.yml" "$LANGFUSE_COMPOSE"
    else
      # Download from GitHub
      curl -fsSL "https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/docker-compose.langfuse.yml" -o "$LANGFUSE_COMPOSE"
    fi
  fi
  
  # Generate secrets if .env doesn't exist
  LANGFUSE_ENV="${LANGFUSE_DIR}/.env"
  if [[ ! -f "$LANGFUSE_ENV" ]]; then
    cat > "$LANGFUSE_ENV" <<ENVFILE
# Langfuse secrets — generated by hermes-cortex installer
# Change these for production!
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_REDIS_AUTH=$(openssl rand -hex 16)
LANGFUSE_MINIO_ACCESS_KEY=minioadmin
LANGFUSE_MINIO_SECRET_KEY=$(openssl rand -hex 32)

# Initial project API keys (auto-created on first run)
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-$(openssl rand -hex 16)
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-$(openssl rand -hex 32)
LANGFUSE_INIT_PROJECT_NAME=Hermes Agent
ENVFILE
    chmod 600 "$LANGFUSE_ENV"
  fi
  
  # Start Langfuse
  cd "$LANGFUSE_DIR"
  if docker compose up -d 2>&1; then
    ok
    info "  Langfuse starting — wait ~30s for all containers"
  else
    warn "Docker Compose failed — install Docker Desktop or check daemon"
  fi
  cd - > /dev/null
fi

# ─────────────────────────────────────────────────────────────
#  13. Cortex Dashboard — Flask companion app
# ─────────────────────────────────────────────────────────────
step "Installing Cortex Dashboard"

DASHBOARD_DEST="${HERMES_HOME}/dashboard"
DASHBOARD_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist"

if [[ -f "$DASHBOARD_DEST/server.py" ]]; then
  skip "Cortex Dashboard already installed"
else
  mkdir -p "$DASHBOARD_DEST"
  
  # Copy from repo
  REPO_DASHBOARD="${CORTEX_HOME}/Developer/AI/hermes-cortex/dashboard"
  if [[ -d "$REPO_DASHBOARD" ]]; then
    cp -r "$REPO_DASHBOARD/"* "$DASHBOARD_DEST/"
  else
    # Download minimal version from GitHub
    curl -fsSL "https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/dashboard/server.py" -o "$DASHBOARD_DEST/server.py"
    curl -fsSL "https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/dashboard/com.hermes.cortex-dashboard.plist" -o "$DASHBOARD_PLIST"
    mkdir -p "$DASHBOARD_DEST/static"
    curl -fsSL "https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/dashboard/static/index.html" -o "$DASHBOARD_DEST/static/index.html"
  fi
  
  # Create dedicated dashboard venv + install Flask
  if [[ ! -f "${DASHBOARD_DEST}/venv/bin/python3" ]]; then
    info "  Creating dedicated dashboard venv…"
    python3 -m venv "${DASHBOARD_DEST}/venv"
    "${DASHBOARD_DEST}/venv/bin/pip" install flask --quiet
    info "  Dashboard venv ready"
  fi

  # Install launchd plist
  if [[ ! -f "$DASHBOARD_PLIST" ]]; then
    # Update paths in plist for current user
    sed "s|CORTEX_HOME|${CORTEX_HOME}|g" "${REPO_DASHBOARD}/com.hermes.cortex-dashboard.plist" > "$DASHBOARD_PLIST" 2>/dev/null || \
    cat > "$DASHBOARD_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.cortex-dashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>${DASHBOARD_DEST}/venv/bin/python3</string>
        <string>${DASHBOARD_DEST}/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${DASHBOARD_DEST}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${HERMES_HOME}/logs/cortex-dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>${HERMES_HOME}/logs/cortex-dashboard.log</string>
</dict>
</plist>
PLIST
  fi
  
  # Load launchd service
  launchctl unload "$DASHBOARD_PLIST" 2>/dev/null || true
  if launchctl load "$DASHBOARD_PLIST" 2>&1; then
    ok
    info "  Dashboard running at http://localhost:8901"
  else
    warn "Failed to load dashboard launchd service"
  fi
fi
else
  skip "Langfuse + Dashboard (laptop profile — Docker not required)"
fi

# ─────────────────────────────────────────────────────────────
#  13. Offline Knowledge Tools — cache cascade + ZIM content
# ─────────────────────────────────────────────────────────────
step "Installing offline knowledge tools (cache cascade + ZIM viewer)"

OFFLINE_REPO="${SCRIPT_DIR}/offline"
OFFLINE_DEST="${HERMES_HOME}/offline"

if [[ -d "$OFFLINE_REPO" ]]; then
  mkdir -p "$OFFLINE_DEST" "$HERMES_BIN"

  # Copy offline knowledge cascade tool
  cp "${OFFLINE_REPO}/offline_knowledge.py" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/offline_knowledge.py"
  cp "${OFFLINE_REPO}/offline_knowledge.sh" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/offline_knowledge.sh"
  ln -sf "${OFFLINE_DEST}/offline_knowledge.sh" "${HERMES_BIN}/offline_knowledge"
  info "  Installed offline knowledge cascade tool"

  # Copy kiwix Docker compose file
  cp "${OFFLINE_REPO}/kiwix-docker-compose.yml" "$OFFLINE_DEST/"
  info "  Installed kiwix-serve Docker compose"

  # Copy prep-offline script
  cp "${OFFLINE_REPO}/prep-offline.sh" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/prep-offline.sh"
  ln -sf "${OFFLINE_DEST}/prep-offline.sh" "${HERMES_BIN}/prep-offline"
  info "  Installed prep-offline content downloader"

  # Copy SKILL.md for Hermes agent
  SKILL_DEST="${HERMES_SKILLS}/software-development"
  mkdir -p "$SKILL_DEST"
  if [[ ! -f "${SKILL_DEST}/SKILL.md" ]] || ! grep -q "offline-knowledge" "${SKILL_DEST}/SKILL.md" 2>/dev/null; then
    cp "${OFFLINE_REPO}/SKILL.md" "${SKILL_DEST}/offline-knowledge.SKILL.md" 2>/dev/null || true
  fi
  info "  Installed offline-knowledge skill"

  # Create offline directories for ZIM content
  mkdir -p "${HOME}/offline/zim"

  # Prompt user to run prep-offline
  printf "\n"
  info "  Offline tools installed."
  info "  To download ZIM content (Wikipedia, WikiMed, Wikivoyage, etc.), run:"
  info "    ${HERMES_BIN}/prep-offline"
  info "  Or with a preset:"
  info "    ${HERMES_BIN}/prep-offline --mode=travel    # Jungle/vacation bundle (~6 GB)"
  info "    ${HERMES_BIN}/prep-offline --mode=build     # Dev offline bundle (~7 GB)"
  info "    ${HERMES_BIN}/prep-offline --mode=education  # Kid learning bundle (~5 GB)"
  printf "\n"
  ok
else
  skip "no offline/ directory in repo"
fi

# ─────────────────────────────────────────────────────────────
#  14. nginx — Reverse proxy for Langfuse + Dashboard
# ─────────────────────────────────────────────────────────────
if [[ "$CORTEX_PROFILE" == "server" ]]; then
step "Installing nginx reverse proxy"
bash "${SCRIPT_DIR}/scripts/install-nginx.sh"
ok
else
  skip "nginx (laptop profile — not needed)"
fi

# ─────────────────────────────────────────────────────────────
#  15. Enable Hermes Plugin
# ─────────────────────────────────────────────────────────────
step "Enabling gbrain-command plugin in Hermes config"

HERMES_CONFIG="${HERMES_HOME}/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
  # Check if plugin is already enabled
  if grep -q "gbrain-command" "$HERMES_CONFIG" 2>/dev/null; then
    skip "plugin already enabled in config"
  else
    # Add gbrain-command to the plugins enabled list
    if grep -q "plugins:" "$HERMES_CONFIG"; then
      # Insert into existing plugins section
      sed -i '' 's/\(enabled:.*\)/\1\n  - gbrain-command/' "$HERMES_CONFIG" 2>/dev/null || \
        warn "Could not auto-edit config.yaml. Manually add 'gbrain-command' under plugins.enabled"
    else
      warn "Could not find plugins section in config.yaml. Manually add:"
      warn "  plugins:"
      warn "    enabled:"
      warn "    - gbrain-command"
    fi
    ok
  fi
else
  warn "config.yaml not found at ${HERMES_CONFIG}. Plugin files are installed but not enabled."
  warn "Manually add 'gbrain-command' under plugins.enabled in your Hermes config."
fi

# ─────────────────────────────────────────────────────────────
#  16. Summary & Next Steps
# ─────────────────────────────────────────────────────────────
header "INSTALLATION SUMMARY"

printf "\n${BOLD}✅ System components installed${RESET}\n"
printf "  ${GREEN}•${RESET} Ollama           — LLM server (embedding: nomic-embed-text)\n"
printf "  ${GREEN}•${RESET} Bun              — JS runtime\n"
printf "  ${GREEN}•${RESET} gbrain           — Knowledge brain (PGLite)\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf "  ${GREEN}•${RESET} Langfuse         — LLM observability (Docker, port 3000)\n"
printf "  ${GREEN}•${RESET} Cortex Dashboard — Flask companion app (port 8901)\n"
printf "  ${GREEN}•${RESET} nginx            — Reverse proxy (ports 11002, 11003)\n"
fi
printf "  ${GREEN}•${RESET} Brain sources    → ${BRAIN_DIR}/{%s}\n" "$(echo "${SOURCES[*]}" | tr ' ' ',')"
printf "  ${GREEN}•${RESET} gbrain plugin    → /brain slash command\n"
printf "  ${GREEN}•${RESET} heartbeat.py     → system health watchdog\n"
printf "  ${GREEN}•${RESET} memory-to-brain.py → memory sync to gbrain\n"
printf "  ${GREEN}•${RESET} memory seeds     → ~/.hermes/memories/{MEMORY,USER}.md\n"
printf "  ${GREEN}•${RESET} Hermes skills    → 8 shared skills in ~/.hermes/skills/\n"
printf "  ${GREEN}•${RESET} Web Cache       → semantic web result cache (sqlite-vec + Ollama)\n"
printf "  ${GREEN}•${RESET} Offline Knowledge → cascade cache + kiwix ZIM content viewer\n"
printf "  ${GREEN}•${RESET} Launchd services:\n"
printf "                   com.ollama.serve\n"
printf "                   com.gbrain.sync-watch\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf "                   com.hermes.cortex-dashboard\n"
printf "                   homebrew.mxcl.nginx\n"
fi
printf "\n"

printf "${BOLD}${YELLOW}⚠ Next Steps — give this prompt to your Hermes Agent:${RESET}\n"
printf "%s${BOLD}${CYAN}" "───────────────────────────────────────────────────"
cat <<PROMPT

I've installed the Hermes Cortex system. Please finish the setup by:

1. Open ~/.hermes/memories/MEMORY.md and ~/.hermes/memories/USER.md — fill in your system topology and user profile so I know your context
2. Load the shared skills from ~/.hermes/skills/ (use skill_view(name) to browse them — includes subagent-driven-development, systematic-debugging, test-driven-development, spike, plan, writing-plans, memory-architecture, requesting-code-review)
3. Loading the hermes-agent skill and verifying the gbrain-command plugin
4. Setting up these cron jobs (use the cronjob tool):

   a) gbrain-nightly-dream — daily at 3am:
      Schedule: 0 3 * * *
      Prompt: Run gbrain maintenance: cd ~ && ~/.bun/bin/bun ~/.bun/bin/gbrain sync --all --parallel 4 --no-pull && ~/.bun/bin/bun ~/.bun/bin/gbrain dream
      Workdir: ~

   b) system-heartbeat — every 30 minutes:
      Schedule: */30 * * * *
      Script: heartbeat.py
      no_agent: true

   c) memory-to-brain-sync — every 6 hours:
      Schedule: 0 */6 * * *
      Script: memory-to-brain.py
      no_agent: true

   d) memory-pruning — daily at 4am:
      Schedule: 0 4 * * *
      Prompt: Read your current MEMORY.md and USER.md from ~/.hermes/memories/ and prune/consolidate entries that are stale, redundant, or no longer relevant. Keep useful durable facts. Report what you removed and why.

5. Run /reset or /new to activate the /brain slash command
6. Verify: run /brain hello-world to test

PROMPT
printf "${RESET}${BOLD}${CYAN}───────────────────────────────────────────────────${RESET}\n"

printf "\n${BOLD}📚 Quick Reference${RESET}\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf "  ${GREEN}•${RESET} Langfuse:        http://localhost:3000 (nginx: :11002)\n"
printf "  ${GREEN}•${RESET} Cortex Dashboard: http://localhost:8901 (nginx: :11003)\n"
fi
printf "  ${GREEN}•${RESET} /brain query     — search your knowledge brain\n"
printf "  ${GREEN}•${RESET} Offline query:   offline_knowledge query \"question\"\n"
printf "  ${GREEN}•${RESET} Download ZIM:    prep-offline\n"
printf "  ${GREEN}•${RESET} Brain dirs:      %s\n" "${BRAIN_DIR}"
printf "  ${GREEN}•${RESET} Logs:            %s/logs/\n" "${HERMES_HOME}"
printf "  ${GREEN}•${RESET} Scripts:         %s/scripts/\n" "${SCRIPTS_DIR}"

printf "\n${BOLD}🐚 For daily use in shell:${RESET}\n"
printf "  Add to ~/.zshrc or ~/.bash_profile:\n"
printf "${YELLOW}  export PATH=\"\$HOME/.bun/bin:\$HOME/.hermes/bin:\$PATH\"${RESET}\n"

printf "\n${GREEN}${BOLD}Hermes Cortex v${VERSION} installed. Enjoy! 🧠${RESET}\n"

# Clear the EXIT trap
trap - EXIT
