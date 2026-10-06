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
while IFS= read -r skill_file; do
  skill_name="${skill_file#"$HOME/.hermes/skills/"}"
  skill_name="${skill_name%/SKILL.md}"
  SKILL_COUNT=$((SKILL_COUNT + 1))
  CUSTOM_COUNT=$((CUSTOM_COUNT + 1))
  CUSTOM_SKILLS+=("$skill_name")
done < <(find "$HOME/.hermes/skills" -name "SKILL.md" -type f 2>/dev/null | sort || true)

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
