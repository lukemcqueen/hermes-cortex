#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Offline Code Corpus Prep
#
#  Generates code snippets and builds the search index.
#
#  Usage:
#    ./prep-code.sh                  # Generate snippets + index
#    ./prep-code.sh --index-only     # Just rebuild index
#    ./prep-code.sh --force          # Force reindex
# ─────────────────────────────────────────────────────────────
set -euo pipefail

HOME="${HOME:-$(echo ~)}"
HERMES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORPUS_DIR="$HERMES_DIR/offline/code-corpus"
CODE_CLI="$HERMES_DIR/offline/offline_code.py"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
header(){ printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }

INDEX_ONLY=0
FORCE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --index-only) INDEX_ONLY=1 ;;
        --force) FORCE="--force" ;;
        -h|--help)
            echo "Usage: $(basename "$0") [--index-only] [--force]"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
    shift
done

header "CODE CORPUS PREP"

# Generate snippet files
if [[ $INDEX_ONLY -eq 0 ]]; then
    echo "  Generating code snippets..."
    python3 "$CORPUS_DIR/generate.py" 2>&1 || {
        warn "Generation had issues"
    }
fi

# Build the search index
echo "  Building search index..."
python3 "$CODE_CLI" index $FORCE 2>&1 || {
    echo "  Index build completed (with warnings)"
}

# Stats
python3 "$CODE_CLI" stats 2>&1

echo ""
info "Code corpus ready"
echo "  Search:  offline_code search \"flask rest api\""
echo "  Gen:     offline_code gen \"binary search tree rust\""
echo "  Stats:   offline_code stats"
echo ""
