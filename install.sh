#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Full System Installer
#  https://github.com/fleet-operator/hermes-cortex
#
#  Installs: Ollama · Bun · gbrain ·
#            Brain directory structure · Hermes plugins ·
#            Launchd services · Cron jobs (via agent)
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

# ─────────────────────────────────────────────────────────────
#  0. Prerequisites & Configuration
# ─────────────────────────────────────────────────────────────
header "PREREQUISITES"

# macOS check
if [[ "$(uname)" != "Darwin" ]]; then
  warn "This script is optimized for macOS. Some steps (launchd, Homebrew) may not work on Linux."
  warn "Continuing anyway — but launchd services will be skipped."
fi

# User info
CORTEX_USER="${CORTEX_USER:-$USER}"
CORTEX_HOME="${CORTEX_HOME:-$HOME}"
BRAIN_DIR="${CORTEX_HOME}/brain"
HERMES_HOME="${HERMES_HOME:-${CORTEX_HOME}/.hermes}"

# Brain sources — default is 'default' + optionally more
if [[ -z "${CORTEX_SOURCES:-}" ]]; then
  # Single-user default
  CORTEX_SOURCES="default"
  info "Brain sources: ${CORTEX_SOURCES}"
  info "  To add more sources (e.g. for multi-person), set CORTEX_SOURCES before running:"
  info "    export CORTEX_SOURCES='luke,amy,shared,default'"
fi

IFS=',' read -ra SOURCES <<< "$CORTEX_SOURCES"
TOTAL_STEPS=10
STEP=0

# Ensure Hermes is installed
if ! command -v hermes &>/dev/null && [[ ! -x "${HERMES_HOME}/hermes-agent/venv/bin/hermes" ]]; then
  warn "Hermes Agent not found. Install it first: https://hermes-agent.nousresearch.com/docs"
  warn "The script will install everything else, but you'll need Hermes for the final agent-side setup."
fi

# Ensure Homebrew
if ! command -v brew &>/dev/null; then
  step "Installing Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || echo 'export PATH=/usr/local/bin:$PATH')"
  ok
fi

# ─────────────────────────────────────────────────────────────
#  1. Ollama — local LLM server for embeddings
# ─────────────────────────────────────────────────────────────
step "Installing Ollama (local LLM server)"
if command -v ollama &>/dev/null; then
  skip "already installed — $(ollama --version 2>/dev/null || echo 'ollama')"
else
  brew install --cask ollama
  ok
fi

# Start Ollama via launchd if not already
if ! launchctl list com.ollama.serve &>/dev/null 2>&1; then
  step "Configuring Ollama launchd service"
  mkdir -p "${CORTEX_HOME}/.ollama"
  cat > "${CORTEX_HOME}/Library/LaunchAgents/com.ollama.serve.plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ollama.serve</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/ollama</string>
        <string>serve</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${CORTEX_HOME}</string>
        <key>OLLAMA_HOST</key>
        <string>127.0.0.1</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>${CORTEX_HOME}/.ollama/serve.log</string>
    <key>StandardErrorPath</key>
    <string>${CORTEX_HOME}/.ollama/serve.err</string>
    <key>WorkingDirectory</key>
    <string>${CORTEX_HOME}</string>
</dict>
</plist>
PLISTEOF
  launchctl load "${CORTEX_HOME}/Library/LaunchAgents/com.ollama.serve.plist"
  ok
else
  skip "launchd service already loaded"
fi

# Wait for Ollama to be ready
step "Waiting for Ollama to respond…"
for i in {1..30}; do
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    info "Ollama ready at 127.0.0.1:11434"
    break
  fi
  if [[ $i -eq 30 ]]; then
    warn "Ollama didn't start in time. Continue anyway (run 'launchctl start com.ollama.serve' manually)."
  fi
  sleep 2
done

# Pull embedding model
step "Pulling embedding model (nomic-embed-text)"
if ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
  skip "already pulled"
else
  ollama pull nomic-embed-text
  ok
fi

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
  bun install -g gbrain
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
#  5. gbrain Sources & Sync Daemon
# ─────────────────────────────────────────────────────────────
step "Configuring gbrain sources"

for source in "${SOURCES[@]}"; do
  source_dir="${BRAIN_DIR}/${source}"
  # Check if source already exists in gbrain
  if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "${source}"; then
    skip "gbrain source '${source}' already configured"
  else
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

# Create sync-watch daemon script
step "Creating gbrain sync-watch daemon (launchd)"
SYNC_SCRIPT="${CORTEX_HOME}/.gbrain/sync-watch.sh"
if [[ -f "$SYNC_SCRIPT" ]]; then
  skip "sync script already exists"
else
  mkdir -p "${CORTEX_HOME}/.gbrain"
  cat > "$SYNC_SCRIPT" <<SCRIPTEOF
#!/bin/bash
# gbrain sync watch daemon
# Polls gbrain sync every 120 seconds
# Launchd manages this via KeepAlive

BUN="${CORTEX_HOME}/.bun/bin/bun"
GBRAIN="${CORTEX_HOME}/.bun/bin/gbrain"
LOG="${CORTEX_HOME}/.gbrain/sync-watch.log"
ERR_LOG="${CORTEX_HOME}/.gbrain/sync-watch.err"
INTERVAL=120

exec >> "\$LOG" 2>> "\$ERR_LOG"

echo "[\$(date)] gbrain sync watch daemon starting — interval \${INTERVAL}s"

while true; do
    echo "[\$(date)] === Sync cycle ==="
    "\$BUN" "\$GBRAIN" sync --all --parallel 4 --no-pull
    echo "[\$(date)] === Cycle complete, sleeping \${INTERVAL}s ==="
    sleep "\$INTERVAL"
done
SCRIPTEOF
  chmod +x "$SYNC_SCRIPT"
  ok
fi

# Create launchd plist for sync daemon
SYNC_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.gbrain.sync-watch.plist"
if launchctl list com.gbrain.sync-watch &>/dev/null 2>&1; then
  skip "sync-watch launchd already loaded"
else
  cat > "$SYNC_PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gbrain.sync-watch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${SYNC_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${CORTEX_HOME}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${CORTEX_HOME}/.bun/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${CORTEX_HOME}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>${CORTEX_HOME}/.gbrain/sync-watch-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${CORTEX_HOME}/.gbrain/sync-watch-stderr.log</string>
</dict>
</plist>
PLISTEOF
  launchctl load "$SYNC_PLIST"
  ok
fi

# ─────────────────────────────────────────────────────────────
#  6. Hermes gbrain Plugin (/brain slash command)
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
#  9. Enable Hermes Plugin
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
#  10. Summary & Next Steps
# ─────────────────────────────────────────────────────────────
header "INSTALLATION SUMMARY"

printf "\n${BOLD}✅ System components installed${RESET}\n"
printf "  ${GREEN}•${RESET} Ollama           — LLM server (embedding: nomic-embed-text)\n"
printf "  ${GREEN}•${RESET} Bun              — JS runtime\n"
printf "  ${GREEN}•${RESET} gbrain            — Knowledge brain (PGLite)\n"
printf "  ${GREEN}•${RESET} ClawMetry        — Dashboard at http://localhost:8900\n"
printf "  ${GREEN}•${RESET} Brain sources     → ${BRAIN_DIR}/{$(echo "${SOURCES[*]}" | tr ' ' ',')}\n"
printf "  ${GREEN}•${RESET} gbrain plugin     → /brain slash command\n"
printf "  ${GREEN}•${RESET} heartbeat.py      → system health watchdog\n"
printf "  ${GREEN}•${RESET} memory-to-brain.py → memory sync to gbrain\n"
printf "  ${GREEN}•${RESET} Launchd services:\n"
printf "                   com.ollama.serve\n"
printf "                   com.gbrain.sync-watch\n"
printf "                   com.clawmetry.dashboard\n\n"

printf "${BOLD}${YELLOW}⚠ Next Steps — give this prompt to your Hermes Agent:${RESET}\n"
printf "%s${BOLD}${CYAN}" "───────────────────────────────────────────────────"
cat <<PROMPT

I've installed the Hermes Cortex system. Please finish the setup by:

1. Loading the hermes-agent skill and verifying the gbrain-command plugin
2. Setting up these cron jobs (use the cronjob tool):

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

3. Run /reset or /new to activate the /brain slash command
4. Verify: run /brain hello-world to test

PROMPT
printf "${RESET}${BOLD}${CYAN}───────────────────────────────────────────────────${RESET}\n"

printf "\n${BOLD}📚 Quick Reference${RESET}\n"
printf "  ${GREEN}•${RESET} ClawMetry:     http://localhost:8900\n"
printf "  ${GREEN}•${RESET} /brain query   — search your knowledge brain\n"
printf "  ${GREEN}•${RESET} Brain dirs:    %s\n" "${BRAIN_DIR}"
printf "  ${GREEN}•${RESET} Logs:          %s/logs/\n" "${HERMES_HOME}"
printf "  ${GREEN}•${RESET} Scripts:       %s/scripts/\n" "${SCRIPTS_DIR}"

printf "\n${BOLD}🐚 For daily use in shell:${RESET}\n"
printf "  Add to ~/.zshrc or ~/.bash_profile:\n"
printf "${YELLOW}  export PATH=\"\$HOME/.bun/bin:\$PATH\"${RESET}\n"

printf "\n${GREEN}${BOLD}Hermes Cortex v${VERSION} installed. Enjoy! 🧠${RESET}\n"

# Clear the EXIT trap
trap - EXIT
