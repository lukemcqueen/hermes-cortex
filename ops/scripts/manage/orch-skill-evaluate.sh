#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-skill-evaluate.sh — Collect skill reports + fleet
#  skill inventory for the LLM evaluator cron.
#
#  Designed to run as no_agent=false cron: the script's stdout
#  is injected as context for the LLM prompt, which then
#  evaluates each skill and decides on upstreaming.
#
#  Dependencies: orch-skill-report-process.py
#
#  Usage:
#    bash orch-skill-evaluate.sh              # normal run
#    bash orch-skill-evaluate.sh --mark-read  # archive processed reports
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || true)")" && pwd)"
MARK_READ=false
for arg; do
  [[ "$arg" == "--mark-read" ]] && MARK_READ=true
done

echo "━━━ orch-skill-evaluate ━━━"
echo ""

# ── Phase 1: Collect pending skill reports ─────────────────
echo "## Phase 1 — Pending Skill Reports"
echo ""

if $MARK_READ; then
  python3 "$SCRIPT_DIR/orch-skill-report-process.py" --mark-read 2>&1 || echo "(collector encountered an error — see above)"
else
  python3 "$SCRIPT_DIR/orch-skill-report-process.py" 2>&1 || echo "(collector encountered an error — see above)"
fi

echo ""

# ── Phase 2: Fleet skill inventory ─────────────────────────
echo "## Phase 2 — Fleet Skill Inventory"
echo ""

# Count all skills and identify custom ones
# NOTE: scan the FULL tree — skills live both at the top level and nested in
# category dirs (e.g. skills/security/1password/SKILL.md). A prior -maxdepth 2
# only matched top-level skills (36 of 511), silently under-reporting the
# inventory by ~93% (fixed 2026-10-06). Skill name is reported as its path
# relative to skills/ so the category is unambiguous.
SKILL_COUNT=0
CUSTOM_COUNT=0
CUSTOM_SKILLS=()
SKILLS_ROOT="$HOME/.hermes/skills"
# Fail loudly, not silently: an unreadable/missing skills root must not be
# reported as "0 skills" (that is indistinguishable from a genuinely empty
# inventory and hides permission/dir errors — SOUL Principle 12).
if [[ ! -d "$SKILLS_ROOT" ]]; then
  echo "ERROR: skills root not found: $SKILLS_ROOT" >&2
  exit 1
fi
if [[ ! -r "$SKILLS_ROOT" ]]; then
  echo "ERROR: skills root not readable: $SKILLS_ROOT" >&2
  exit 1
fi
# Capture find's stderr via a temp file (a process-substitution subshell
# cannot assign back to the parent — that was the first, broken attempt).
FIND_ERR_FILE="$(mktemp)"
trap 'rm -f "$FIND_ERR_FILE"' EXIT
while IFS= read -r skill_file; do
  skill_name="${skill_file#"$SKILLS_ROOT/"}"
  skill_name="${skill_name%/SKILL.md}"
  SKILL_COUNT=$((SKILL_COUNT + 1))
  CUSTOM_COUNT=$((CUSTOM_COUNT + 1))
  CUSTOM_SKILLS+=("$skill_name")
done < <(find "$SKILLS_ROOT" -name "SKILL.md" -type f 2>"$FIND_ERR_FILE" | sort)
if [[ -s "$FIND_ERR_FILE" ]]; then
  echo "WARN: find reported errors while scanning $SKILLS_ROOT:" >&2
  sed 's/^/    /' "$FIND_ERR_FILE" >&2
fi
if [[ "$SKILL_COUNT" -eq 0 ]]; then
  echo "WARN: 0 SKILL.md files found under $SKILLS_ROOT — inventory may be wrong" >&2
fi

echo "Total skills: $SKILL_COUNT"
echo "Custom/local skills: $CUSTOM_COUNT"

if [[ ${#CUSTOM_SKILLS[@]} -gt 0 ]]; then
  echo ""
  echo "Custom skills found:"
  for s in "${CUSTOM_SKILLS[@]}"; do
    echo "- $s"
  done
fi

echo ""
echo "---"
echo "*orch-skill-evaluate.sh complete — LLM will now evaluate the above*"
