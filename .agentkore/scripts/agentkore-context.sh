#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
PROJECT_ROOT="$(pwd)"
echo "Repo root: $REPO_ROOT"
cd "$PROJECT_ROOT"
echo "Project root: $PROJECT_ROOT"
echo

echo "== AgentKore Config =="
cat .agentkore/config/agentkore.json 2>/dev/null || true
echo
echo "== Current Task =="
cat .agentkore/runtime/current_task.md 2>/dev/null || echo "No current task."
echo
echo "== Git Status =="
git status --short 2>/dev/null || echo "Not a git repo."
echo
echo "== Skill List ==="
for d in .opencode/skills/*/; do
  name=$(basename "$d")
  desc=$(sed -n 's/^description: *//p' "$d/SKILL.md" 2>/dev/null | head -1)
  printf "  %-35s %s\n" "$name" "$desc"
done
