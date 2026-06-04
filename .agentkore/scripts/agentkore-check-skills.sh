#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(pwd)"
echo "== AgentKore Skill Discovery Check =="
echo "Project root: $PROJECT_ROOT"
echo

if [ ! -d .opencode/skills ]; then
  echo "MISSING: .opencode/skills"
  exit 1
fi

echo "Installed OpenCode skills:"
find .opencode/skills -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | sed 's#^\.opencode/skills/##; s#/SKILL.md$##' | sort

echo
for skill in agent-contract agent-flow change-test-loop git-workflow security; do
  path=".opencode/skills/$skill/SKILL.md"
  if [ -f "$path" ]; then
    : # ok
  else
    echo "MISSING: $skill ($path)"
  fi
done

echo
echo "Checking opencode.json skill permission..."
python3 - <<'PY'
import json
from pathlib import Path
p=Path('opencode.json')
if not p.exists():
    raise SystemExit('opencode.json missing')
data=json.loads(p.read_text())
perm=data.get('permission',{}).get('skill')
print(perm)
if perm != {'*':'allow'}:
    raise SystemExit("Expected permission.skill to be {'*':'allow'}")
PY

echo
echo "For full validation: .agentkore/scripts/agentkore-validate.sh"
