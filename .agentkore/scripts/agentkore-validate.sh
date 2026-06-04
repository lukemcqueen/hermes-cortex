#!/usr/bin/env bash
set -uo pipefail

PROJECT_ROOT="$(pwd)"
echo "Project root: $PROJECT_ROOT"
echo

ERRORS=0
WARNINGS=0

err(){ ERRORS=$((ERRORS+1)); echo "ERROR: $1"; echo "FIX:   $2"; echo; }
warn(){ WARNINGS=$((WARNINGS+1)); echo "WARN:  $1"; echo "FIX:   $2"; echo; }
ok(){ echo "  OK: $1"; }
require_file(){ [ -f "$1" ] && ok "$1" || err "Missing file: $1" "$2"; }
require_dir(){ [ -d "$1" ] && ok "$1/" || err "Missing directory: $1" "$2"; }

if [ ! -f AGENTS.md ]; then
  err "Not at AgentKore project root" "Run this script from the directory containing AGENTS.md."
fi

echo "== AgentKore Validation =="

for d in .agentkore .agentkore/config .agentkore/prompts .agentkore/sessions .opencode .opencode/skills .opencode/commands .opencode/agents docs memory .agentkore/scripts; do
  require_dir "$d" "Run .agentkore/scripts/agentkore-init.sh or restore AgentKore package."
done

for f in AGENTS.md opencode.json .agentkore/config/agentkore.json .agentkore/config/routing.md .agentkore/config/modes.md .agentkore/prompts/system.md; do
  require_file "$f" "Restore $f from AgentKore package."
done

# Core skills (always required)
CORE_SKILLS="agent-contract agent-flow bash-shell change-test-loop code-review debugging doc-system fast-bmad git-workflow memory-management repo-discovery security session-manager state-orchestrator task-executor testing-strategy"

echo
echo "== Skills =="

# Validate core skills are present
for skill in $CORE_SKILLS; do
  primary=".opencode/skills/$skill/SKILL.md"
  require_file "$primary" "Create $primary with YAML frontmatter: name: $skill and description."
  if [ -f "$primary" ]; then
    first_line="$(sed -n '1p' "$primary")"
    [ "$first_line" = "---" ] || err "$primary must start with YAML frontmatter" "Remove chat prose/code fences before the frontmatter."
    grep -q "^name: $skill$\|^name: ${skill%-lite}$\|^name: ${skill%-to-tasks}$" "$primary" || err "$primary mismatched name" "Set name: $skill"
    grep -q '^description:' "$primary" || err "$primary missing description" "Add description."
  fi
done

# Check optional skills (warn if in skills/ but not in optional-skills catalog)
for s in .opencode/skills/*/; do
  name=$(basename "$s")
  # Skip core skills — already validated
  case " $CORE_SKILLS " in
    *" $name "*) continue ;;
  esac
  if [ ! -d ".opencode/optional-skills/$name" ]; then
    warn "Installed skill '$name' has no matching optional-skills catalog" "Either add to .opencode/optional-skills/$name or remove from .opencode/skills/."
  fi
done

if [ -e .opencode/skills/docs-memory-workflow ] || [ -e .opencode/commands/docs-memory-workflow.md ]; then
  err "Deprecated docs-memory-workflow still exists" "Remove it; use state-orchestrator + doc-system + memory-management."
fi

STALE_TMP="$(mktemp)"
trap 'rm -f "$STALE_TMP"' EXIT
if grep -RniE '(^|[^a-zA-Z0-9_-])gent-contract([^a-zA-Z0-9_-]|$)|docs-memory-workflow' AGENTS.md .opencode .agentkore docs memory 2>/dev/null | grep -v 'Deprecated / removed' | grep -v 'docs-memory-workflow was removed' | grep -v 'Deprecated docs-memory-workflow still exists' | grep -v 'docs-memory-workflow.md' | grep -v 'docs-memory-workflow` was removed' | grep -v 'DOCS-MEMORY-WORKFLOW-TEMPLATE' >"$STALE_TMP"; then
  err "Stale skill references found" "Review stale references and remove them."
  cat "$STALE_TMP"
fi

echo
echo "== Commands =="





REQUIRED_COMMANDS="agentkore plan execute-task debug review release-check save-session restore-session proxy-debug check security-review repo-discovery system-update ui design-check"
for cmd in $REQUIRED_COMMANDS; do
  require_file ".opencode/commands/$cmd.md" "Restore .opencode/commands/$cmd.md from package."
done

echo
echo "== JSON config and skill registry sync =="
python3 - <<'PYJSON'
import json, re, sys
from pathlib import Path
errors=[]
for f in ['opencode.json','.agentkore/config/agentkore.json']:
    try:
        json.loads(Path(f).read_text())
    except Exception as e:
        errors.append(f'{f}: {e}')
if not errors:
    cfg=json.loads(Path('.agentkore/config/agentkore.json').read_text())
    disk=sorted(p.parent.name for p in Path('.opencode/skills').glob('*/SKILL.md'))
    cfgskills=sorted(cfg.get('skills', []))
    # Config skills must be a subset of disk skills (disk can have more = optional installed)
    missing_from_disk=[s for s in cfgskills if s not in disk]
    if missing_from_disk:
        errors.append(f'config skills missing from disk: {missing_from_disk}')
    for p in Path('.opencode/skills').glob('*/SKILL.md'):
        txt=p.read_text()
        if not txt.startswith('---\n'):
            errors.append(f'{p} has prose or code fence before frontmatter')
        if not re.search(r'^---\n(.*?)\n---', txt, re.S):
            errors.append(f'{p} missing YAML frontmatter block')
if errors:
    print('PY_ERROR: ' + '; '.join(errors)); sys.exit(1)
print('  PY_OK: JSON config and skill frontmatter are consistent')
PYJSON
[ $? -ne 0 ] && err "JSON/skill validation failed" "Fix invalid JSON or skill frontmatter."

echo
echo "== Summary =="
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
[ "$ERRORS" -eq 0 ] && echo "AgentKore validation passed." || echo "AgentKore validation failed."
exit "$ERRORS"
