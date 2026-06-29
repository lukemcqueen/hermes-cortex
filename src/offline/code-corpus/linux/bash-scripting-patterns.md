---
language: shell
tags: [bash, scripting, patterns]
title: Bash Scripting — Best Practices
description: Robust bash scripts with set -euo pipefail, argument parsing, error handling, and patterns.
source: pattern
---

```bash
#!/usr/bin/env bash
# ── Safety guards ──
set -euo pipefail          # exit on error, undef vars, pipe failures
# set -x                   # uncomment for debug (prints each command)

# ── Configuration ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/script.log"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Argument parsing ──
usage() {
    cat <<EOF
Usage: $(basename "$0") [options] <input>

Options:
  -o, --output FILE    Output file (default: stdout)
  -v, --verbose        Verbose output
  -h, --help           Show this help
EOF
    exit 0
}

# Parse with getopt
PARSED=$(getopt -o o:vh --long output:,verbose,help -n "$0" -- "$@")
eval set -- "$PARSED"
output="" verbose=false
while true; do
    case "$1" in
        -o|--output)  output="$2"; shift 2 ;;
        -v|--verbose) verbose=true; shift ;;
        -h|--help)    usage ;;
        --)           shift; break ;;
    esac
done
INPUT="${1:-}"

# ── Functions ──
cleanup() {
    info "Cleaning up temporary files..."
    rm -f /tmp/script_*.tmp
}
trap cleanup EXIT

# ── Main ──
main() {
    [[ -z "$INPUT" ]] && { error "Missing input argument"; usage; }
    info "Processing $INPUT..."
    # script logic here
}

main "$@"
```
