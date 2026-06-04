#!/usr/bin/env bash
# AgentKore Uninstaller
# Usage: .agentkore/scripts/agentkore-uninstall.sh [--force]
#
# Removes all AgentKore files from the current directory.
# Does NOT affect your project files (src/, tests/, docs/, etc.)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

PROJECT_ROOT="$(pwd)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        AgentKore Uninstaller            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "This will remove AgentKore from: $PROJECT_ROOT"
echo ""

# Safety checks
[ ! -f "$PROJECT_ROOT/AGENTS.md" ] && fail "No AGENTS.md found — not an AgentKore project root."

# Confirm unless --force
FORCE=false
for arg in "$@"; do
  [ "$arg" = "--force" ] && FORCE=true
done

if [ "$FORCE" = false ]; then
  echo "Files to be removed:"
  echo "  - AGENTS.md"
  echo "  - opencode-instructions.md"
  echo "  - opencode.json"
  echo "  - .agentkore/"
  echo "  - .opencode/"
  echo "  - scripts/"
  echo "  - memory/"
  echo "  - docs/design/DESIGN.md"
  echo "  - docs/DOCS-INDEX.md"
  echo ""
  echo "Your project source code, tests, and other files are NOT affected."
  read -rp "Continue? [y/N] " confirm
  [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && echo "Cancelled." && exit 0
fi

# Remove AgentKore files
echo ""
log "Removing AGENTS.md..."
rm -f "$PROJECT_ROOT/AGENTS.md"

log "Removing opencode-instructions.md..."
rm -f "$PROJECT_ROOT/opencode-instructions.md"

log "Removing opencode.json..."
rm -f "$PROJECT_ROOT/opencode.json"

log "Removing .agentkore/..."
rm -rf "$PROJECT_ROOT/.agentkore"

log "Removing .opencode/ (skills + config)..."
rm -rf "$PROJECT_ROOT/.opencode"

log "Removing scripts/..."
rm -rf "$PROJECT_ROOT/scripts"

log "Removing memory/..."
rm -rf "$PROJECT_ROOT/memory"

log "Removing docs/design/DESIGN.md..."
rm -f "$PROJECT_ROOT/docs/design/DESIGN.md"

log "Removing docs/DOCS-INDEX.md..."
rm -f "$PROJECT_ROOT/docs/DOCS-INDEX.md"

# Clean up empty docs/ if left
[ -d "$PROJECT_ROOT/docs" ] && [ -z "$(ls -A "$PROJECT_ROOT/docs")" ] && rmdir "$PROJECT_ROOT/docs" && log "Removed empty docs/"

echo ""
log "AgentKore has been removed from $PROJECT_ROOT"
echo ""
echo "Your project files are untouched."
