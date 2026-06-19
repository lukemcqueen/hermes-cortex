#!/bin/bash
# <Agent Repo> — Hermes Cortex Unified CLI
# Usage: ./run <command>
#
# Minimal variant for agent-only repos (hermes-cortex, docs repos, skill repos).
# No Docker, no database, no frontend — just agent workflows.
# See canonical template at templates/run.sh for full Docker projects.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

# ══════════════════════════════════════════════════════════
# HELP
# ══════════════════════════════════════════════════════════

show_help() {
    cat <<EOF
<Agent Repo> — Unified CLI

Usage: ./run <command>

Validate:
  check               Run all validation checks (lint + schema + spell)
  check:yaml          Validate YAML frontmatter in all files
  check:spell         Check spelling in markdown files
  check:schema        Validate skill/memory schemas

Sweep:
  sweep               Run all maintenance sweeps
  sweep:stale         Find stale cron jobs, skills, memories
  sweep:orphans       Find orphaned references (unreachable docs)

Cortex:
  build               Compile/transform cortex artifacts (if applicable)
  lint                Lint skills, prompts, and config files
  format              Normalize formatting (YAML, markdown, frontmatter)
  test                Run all validation tests
  clean               Remove temporary files and generated artifacts

Utility:
  git:status          Quick status check
  git:sync            Sync with origin (fetch + rebase)
  help                Show this help

Examples:
  ./run check
  ./run lint
  ./run clean
  ./run git:sync
EOF
}

# ══════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════

cmd_check() {
    info "Running all validation checks..."
    cmd_check_yaml || true
    cmd_check_spell || true
    cmd_check_schema || true
    ok "Validation checks complete"
}

cmd_check_yaml() {
    info "Checking YAML frontmatter..."
    local errors=0
    while IFS= read -r -d '' file; do
        if ! python3 -c "
import yaml, re, sys
with open('$file') as f:
    content = f.read()
m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
if not m:
    sys.exit(1)
yaml.safe_load(m.group(1))
" 2>/dev/null; then
            warn "  Invalid YAML: $file"
            errors=$((errors + 1))
        fi
    done < <(find . -name '*.md' -o -name 'SKILL.md' | grep -v node_modules | grep -v .git | head -100)
    [ "$errors" -eq 0 ] && ok "All YAML frontmatter valid" || warn "$errors file(s) with invalid YAML"
}

cmd_check_spell() {
    info "Checking spelling..."
    if command -v codespell &>/dev/null; then
        codespell . --skip=".git,node_modules,.venv" 2>&1 || true
    else
        warn "codespell not installed. Install: pip install codespell"
    fi
    ok "Spell check complete"
}

cmd_check_schema() {
    info "Checking schemas..."
    if [ -f "$PROJECT_ROOT/scripts/validate-schemas.py" ]; then
        python3 "$PROJECT_ROOT/scripts/validate-schemas.py"
    else
        warn "No schema validation script found at scripts/validate-schemas.py"
    fi
    ok "Schema check complete"
}

# ══════════════════════════════════════════════════════════
# SWEEP — Maintenance tasks
# ══════════════════════════════════════════════════════════

cmd_sweep() {
    info "Running all maintenance sweeps..."
    cmd_sweep_stale || true
    cmd_sweep_orphans || true
    ok "Sweep complete"
}

cmd_sweep_stale() {
    info "Checking for stale artifacts..."
    # Skills/memories older than 90 days
    find . -name 'SKILL.md' -mtime +90 -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | while read -r skill; do
        warn "  Stale skill (90+ days unchanged): $skill"
    done
    ok "Stale artifact check complete"
}

cmd_sweep_orphans() {
    info "Checking for orphaned references..."
    if [ -f "$PROJECT_ROOT/scripts/find-orphans.py" ]; then
        python3 "$PROJECT_ROOT/scripts/find-orphans.py"
    else
        warn "No orphan detection script at scripts/find-orphans.py"
    fi
    ok "Orphan check complete"
}

# ══════════════════════════════════════════════════════════
# CORTEX — Build, test, lint
# ══════════════════════════════════════════════════════════

cmd_lint() {
    info "Linting skills and config..."
    local errors=0
    while IFS= read -r -d '' file; do
        if ! python3 -c "
import yaml, sys
with open('$file') as f:
    content = f.read()
# Check for broken YAML in frontmatter (--- delimited)
import re
m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
if m:
    yaml.safe_load(m.group(1))
" 2>/dev/null; then
            warn "  Invalid frontmatter: $file"
            errors=$((errors + 1))
        fi
    done < <(find . -name '*.md' -print0 2>/dev/null | grep -zv 'node_modules\|\.git' | head -100)

    [ "$errors" -eq 0 ] && ok "All files clean" || warn "Lint issues in $errors files"
}

cmd_format() {
    info "Normalizing formatting..."
    # Fix trailing whitespace
    find . -name '*.md' -not -path '*/node_modules/*' -not -path '*/.git/*' -exec sed -i '' 's/[[:space:]]*$//' {} + 2>/dev/null || true
    ok "Formatting normalized"
}

cmd_test() {
    info "Running all tests..."
    # Validate frontmatter on all SKILL.md files
    local errors=0
    while IFS= read -r -d '' file; do
        if head -1 "$file" 2>/dev/null | grep -q '^---$'; then
            python3 -c "
import yaml, re, sys
with open('$file') as f:
    m = re.match(r'^---\s*\n(.*?)\n---', f.read(), re.DOTALL)
if not m: sys.exit(1)
yaml.safe_load(m.group(1))
" 2>/dev/null || { warn "  Failed: $file"; errors=$((errors + 1)); }
        fi
    done < <(find . -name 'SKILL.md' -print0 2>/dev/null | grep -zv 'node_modules\|\.git')

    [ "$errors" -eq 0 ] && ok "All SKILL.md files valid" || error "$errors SKILL.md file(s) invalid"
}

cmd_build() {
    info "Building cortex artifacts..."
    if [ -f "$PROJECT_ROOT/Makefile" ]; then
        make build
    elif [ -f "$PROJECT_ROOT/scripts/build.sh" ]; then
        bash "$PROJECT_ROOT/scripts/build.sh"
    else
        warn "No build script found. Nothing to build."
    fi
    ok "Build complete"
}

# ══════════════════════════════════════════════════════════
# UTILITY
# ══════════════════════════════════════════════════════════

cmd_clean() {
    info "Cleaning temporary files..."
    find . -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete 2>/dev/null || true
    find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
    rm -rf .pytest_cache .ruff_cache .mypy_cache 2>/dev/null || true
    ok "Clean complete"
}

cmd_git_status() {
    info "Git status..."
    cd "$PROJECT_ROOT"
    git status -s
    echo ""
    git log --oneline -5 2>/dev/null || true
}

cmd_git_sync() {
    info "Syncing with origin..."
    cd "$PROJECT_ROOT"
    git fetch origin
    git rebase origin/main 2>/dev/null || git rebase origin/master 2>/dev/null
    ok "Sync complete"
}

# ══════════════════════════════════════════════════════════
# ROUTING
# ══════════════════════════════════════════════════════════

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

CMD="$1"
shift

case "$CMD" in
    # Validate
    check)             cmd_check "$@" ;;
    check:yaml)        cmd_check_yaml "$@" ;;
    check:spell)       cmd_check_spell "$@" ;;
    check:schema)      cmd_check_schema "$@" ;;

    # Sweep
    sweep)             cmd_sweep "$@" ;;
    sweep:stale)       cmd_sweep_stale "$@" ;;
    sweep:orphans)     cmd_sweep_orphans "$@" ;;

    # Cortex
    build)             cmd_build "$@" ;;
    lint)              cmd_lint "$@" ;;
    format)            cmd_format "$@" ;;
    test)              cmd_test "$@" ;;

    # Utility
    clean)             cmd_clean "$@" ;;
    git:status)        cmd_git_status "$@" ;;
    git:sync)          cmd_git_sync "$@" ;;
    help|--help|-h)    show_help ;;

    *)
        error "Unknown command: $CMD"
        echo "Run './run help' for available commands"
        exit 1
        ;;
esac