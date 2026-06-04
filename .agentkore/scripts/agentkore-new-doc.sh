#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(pwd)"
TYPE="${1:-}"
NAME="${2:-}"
if [ -z "$TYPE" ] || [ -z "$NAME" ]; then
  echo "Usage: .agentkore/scripts/agentkore-new-doc.sh prd|architecture|research|adr|decision|task name"
  exit 1
fi

SLUG=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-')
DATE=$(date +"%Y-%m-%d")
mkdir -p docs/prd docs/architecture docs/research docs/decisions docs/tasks

case "$TYPE" in
  prd)
    DEST="docs/prd/${SLUG}.md"
    TEMPLATE=".agentkore/templates/prd/PRD-LITE-TEMPLATE.md"
    ;;
  architecture)
    DEST="docs/architecture/${SLUG}.md"
    TEMPLATE=".agentkore/templates/architecture/ARCHITECTURE-NOTE-TEMPLATE.md"
    ;;
  research)
    DEST="docs/research/${DATE}-${SLUG}.md"
    TEMPLATE=".agentkore/templates/research/RESEARCH-NOTE-TEMPLATE.md"
    ;;
  adr|decision)
    DEST="docs/decisions/${DATE}-${SLUG}.md"
    TEMPLATE=".agentkore/templates/decisions/ADR-TEMPLATE.md"
    ;;
  task)
    DEST="docs/tasks/${SLUG}.md"
    TEMPLATE=".agentkore/templates/tasks/TASK-PLAN-TEMPLATE.md"
    ;;
  *)
    echo "Unknown type: $TYPE"
    exit 1
    ;;
esac

if [ -e "$DEST" ]; then
  echo "Refusing to overwrite existing doc: $DEST"
  exit 1
fi

if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$DEST"
else
  printf '# %s\n\n## Status\n\nStatus: draft\nOwner:\nLast updated: %s\n\n## Related docs\n\n' "$NAME" "$DATE" > "$DEST"
fi

echo "Created $DEST"
