#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Cron Installer
#
#  Reads crons.json and registers crons via hermes cron create.
#  Idempotent: removes existing crons with matching names,
#  then creates fresh ones from the template.
#
#  Usage:
#    bash install-crons.sh              # install
#    bash install-crons.sh --check      # dry-run
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RESET='\033[0m'
pass() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ${RESET} %s\n" "$1"; }

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)"
TEMPLATE="${SOURCE_DIR}/crons.json"
MARKER="${SOURCE_DIR}/.cron-version"

if [[ ! -f "$TEMPLATE" ]]; then fail "Template not found: $TEMPLATE"; exit 1; fi
if ! command -v hermes &>/dev/null; then
  fail "Hermes Agent not found. Install: https://hermes-agent.nousresearch.com"
  exit 1
fi

TEMPLATE_VER=$(python3 -c "import json; print(json.load(open('${TEMPLATE}'))['version'])")
INSTALLED_VER=$(cat "$MARKER" 2>/dev/null || echo "0")

echo ""
echo "═ Loop Governance Crons ═"
echo ""
info "Template v${TEMPLATE_VER}  |  Installed v${INSTALLED_VER}"
echo ""

if [[ "$TEMPLATE_VER" == "$INSTALLED_VER" ]]; then
  pass "Crons are up to date (v${TEMPLATE_VER})"
  exit 0
fi

# ── Parse template ─────────────────────────────────────────
# Read each cron definition from the JSON template
python3 -c "
import json, subprocess, sys

template = json.load(open('${TEMPLATE}'))
crons = template['crons']
version = template['version']

# Store cron details for shell to iterate
for c in crons:
    print(f'CRON:{c[\"name\"]}|{c[\"schedule\"]}|{c.get(\"deliver\",\"origin\")}|{\"no-agent\" if c.get(\"no_agent\") else \"agent\"}|{c.get(\"script\",\"\")}|{\"|\".join(c.get(\"skills\",[]))}')
" 2>/dev/null | while IFS='|' read -r _ NAME SCHED DELIVER MODE SCRIPT SKILLS; do
  [[ -z "$NAME" || "$NAME" == "CRON"* && -z "$SCHED" ]] && continue
  # Strip CRON: prefix if present
  NAME="${NAME#CRON:}"

  if [[ "$CHECK_ONLY" == "1" ]]; then
    info "Would create '$NAME' ($SCHED)"
    continue
  fi

  # Remove existing crons with this name by looking up job IDs
  # from 'hermes cron list' output
  hermes cron list 2>/dev/null | while read -r LINE; do
    # Look for a job ID followed by [active] or [paused]
    if [[ "$LINE" =~ ^[a-f0-9]{12,}\ +\[(active|paused)\] ]]; then
      CURRENT_ID="${LINE%% *}"
    fi
    if echo "$LINE" | grep -q "Name:.*$NAME"; then
      hermes cron remove --job-id "$CURRENT_ID" 2>/dev/null || true
    fi
  done

  # Build create command
  CMD="hermes cron create '$SCHED' --name '$NAME' --deliver '$DELIVER'"

  if [[ "$MODE" == "no-agent" && -n "$SCRIPT" ]]; then
    CMD="$CMD --no-agent --script '$SCRIPT'"
  else
    # Read prompt from template for this cron
    PROMPT=$(python3 -c "
import json
t = json.load(open('${TEMPLATE}'))
for c in t['crons']:
    if c['name'] == '$NAME':
        print(c.get('prompt',''))
" 2>/dev/null)
    if [[ -n "$PROMPT" ]]; then
      # Write prompt to temp file to avoid shell escaping issues
      PF=$(mktemp)
      echo "$PROMPT" > "$PF"
      CMD="$CMD \"$(cat "$PF")\""
      rm -f "$PF"

      # Add skills
      IFS='|' read -ra SKILL_ARRAY <<< "$SKILLS"
      for SKILL in "${SKILL_ARRAY[@]}"; do
        [[ -n "$SKILL" ]] && CMD="$CMD --skill '$SKILL'"
      done
    fi
  fi

  if eval "$CMD" 2>/dev/null; then
    pass "$NAME created ($SCHED)"
  else
    # Retry: sometimes the prompt file approach works better as direct text
    if [[ "$MODE" != "no-agent" ]]; then
      PROMPT=$(python3 -c "
import json
t = json.load(open('${TEMPLATE}'))
for c in t['crons']:
    if c['name'] == '$NAME':
        import shlex
        print(shlex.quote(c.get('prompt','')))
" 2>/dev/null)
      CMD2="hermes cron create '$SCHED' --name '$NAME' --deliver '$DELIVER' $PROMPT"
      IFS='|' read -ra SKILL_ARRAY <<< "$SKILLS"
      for SKILL in "${SKILL_ARRAY[@]}"; do
        [[ -n "$SKILL" ]] && CMD2="$CMD2 --skill '$SKILL'"
      done
      if eval "$CMD2" 2>/dev/null; then
        pass "$NAME created ($SCHED)"
      else
        warn "$NAME — may already exist"
      fi
    fi
  fi
done

# Record version
echo "$TEMPLATE_VER" > "$MARKER"
echo ""
pass "Crons installed (v${TEMPLATE_VER})"
echo ""
info "Verify: hermes cron list | grep -E '(loop|weekly)'"