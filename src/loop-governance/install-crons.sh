#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Cron Installer
#
#  Reads crons.json template and registers crons via
#  `hermes cron create`. Idempotent — updates existing crons.
#
#  Usage:
#    bash install-crons.sh              # install/update crons
#    bash install-crons.sh --check      # check template vs installed
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
pass() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ${RESET} %s\n" "$1"; }

CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in --check) CHECK_ONLY=1;; esac
done

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)"
TEMPLATE="${SOURCE_DIR}/crons.json"
MARKER="${SOURCE_DIR}/.cron-version"

if [[ ! -f "$TEMPLATE" ]]; then
  fail "Template not found: $TEMPLATE"
  exit 1
fi

# Check Hermes is installed
if ! command -v hermes &>/dev/null; then
  fail "Hermes Agent not found. Install it first: https://hermes-agent.nousresearch.com"
  exit 1
fi

TEMPLATE_VER=$(python3 -c "import json; print(json.load(open('${TEMPLATE}'))['version'])")
INSTALLED_VER=$(cat "$MARKER" 2>/dev/null || echo "0")
NEEDS_UPDATE=0

echo ""
echo "═ Loop Governance Crons ═"
echo ""
info "Template v${TEMPLATE_VER}  |  Installed v${INSTALLED_VER}"

# Validate each cron against current state
python3 -c "
import json, subprocess, sys

template = json.load(open('${TEMPLATE}'))
installed_ver = '${INSTALLED_VER}'
check_only = ${CHECK_ONLY}

# List existing jobs
result = subprocess.run(
    ['hermes', 'cron', 'list', '--json'],
    capture_output=True, text=True, timeout=15
)
existing = {}
if result.returncode == 0:
    import json as j
    try:
        jobs = j.loads(result.stdout)
        if isinstance(jobs, list):
            for j in jobs:
                existing[j.get('name','')] = j
        elif isinstance(jobs, dict) and 'jobs' in jobs:
            for j in jobs['jobs']:
                existing[j.get('name','')] = j
    except: pass

for cron in template['crons']:
    name = cron['name']
    exists = name in existing
    status = 'UPDATE' if (exists and check_only) else ('CREATE' if not exists else 'OK')
    print(json.dumps({
        'name': name,
        'exists': exists,
        'needs_update': not exists or installed_ver != str(template['version']),
        'status': status,
        'schedule': cron['schedule'],
        'script': cron.get('script', ''),
        'prompt': cron.get('prompt', ''),
        'skills': cron.get('skills', []),
        'no_agent': cron.get('no_agent', False),
        'deliver': cron.get('deliver', 'origin'),
    }))
" | while read -r LINE; do
  NAME=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
  EXISTS=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['exists'])")
  NEEDS=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['needs_update'])")
  STATUS=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  SCHED=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['schedule'])")
  SCRIPT=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin)['script'])")
  PROMPT=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('prompt',''))")
  SKILLS=$(echo "$LINE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('skills',[])))")
  NO_AGENT=$(echo "$LINE" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('no_agent',False)).lower())")
  DELIVER=$(echo "$LINE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('deliver','origin'))")

  if [[ "$STATUS" == "OK" ]]; then
    pass "${NAME} (up to date)"
    continue
  fi

  if [[ "$CHECK_ONLY" == "1" ]]; then
    if [[ "$EXISTS" == "False" ]]; then
      info "${NAME} → needs creation (${SCHED})"
    else
      info "${NAME} → needs update (${SCHED})"
    fi
    NEEDS_UPDATE=1
    continue
  fi

  # Build command
  if [[ "$EXISTS" == "True" ]]; then
    CMD="hermes cron edit --name '${NAME}'"
  else
    CMD="hermes cron create '${SCHED}' --name '${NAME}' --deliver '${DELIVER}'"
  fi

  if [[ "$NO_AGENT" == "true" && -n "$SCRIPT" ]]; then
    CMD="$CMD --no-agent --script '${SCRIPT}'"
  elif [[ -n "$PROMPT" ]]; then
    # Write prompt to temp file to avoid shell escaping issues
    PF=$(mktemp)
    python3 -c "
import json
p = json.loads('''$(echo "$LINE" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('prompt','')))")''')
with open('${PF}', 'w') as f:
    f.write(p)
" 2>/dev/null
    CMD="$CMD \"$(cat "$PF")\""
    rm -f "$PF"
    SKILLS_LIST=$(echo "$SKILLS" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)))" 2>/dev/null || echo "")
    for SKILL in $SKILLS_LIST; do
      CMD="$CMD --skill '$SKILL'"
    done
  fi

  # Run it
  if eval "$CMD" 2>&1; then
    if [[ "$EXISTS" == "True" ]]; then
      pass "${NAME} updated"
    else
      pass "${NAME} created"
    fi
  else
    warn "${NAME} failed"
    info "  Try: $CMD"
  fi
done

if [[ "$CHECK_ONLY" == "1" ]]; then
  if [[ "$NEEDS_UPDATE" == "1" ]]; then
    echo ""
    info "Run without --check to apply: bash install-crons.sh"
  else
    pass "All crons up to date"
  fi
  exit 0
fi

# Record version
echo "$TEMPLATE_VER" > "$MARKER"
echo ""
pass "Cron version v${TEMPLATE_VER} recorded"
echo ""
info "Verify: hermes cron list | grep loop"