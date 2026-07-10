---
language: shell
tags: [shell, bash, best-practices, scripting]
title: Shell Scripting Best Practices
description: set -euo pipefail, quoting every variable, functions over scripts, error handling, trap cleanup, and argument parsing with getopt
source: pattern
---

# Shell Scripting Best Practices

## Strict Mode
Begin every script with strict mode:

```bash
#!/usr/bin/env bash
set -euo pipefail
#   -e  : exit on first error
#   -u  : treat unset variables as errors
#   -o pipefail : pipeline fails if any command fails
IFS=$'\n\t'  # safer word splitting
```

## Quote Everything
Quote every variable expansion and command substitution:

```bash
# Bad — word splitting and globbing
if [ $name = $other ]; then …

# Good — quoted
if [ "$name" = "$other" ]; then …
result="$(some_command "$arg")"
```

## Functions Over Scripts
Define reusable functions instead of copy-pasting blocks:

```bash
log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') — $*" >&2
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') — $*" >&2
}

die() {
    log_error "$@"
    exit 1
}
```

## Error Handling
Check return codes explicitly and provide meaningful messages:

```bash
mkdir -p "$OUTPUT_DIR" || die "Failed to create output directory: $OUTPUT_DIR"

if ! command -v jq &>/dev/null; then
    die "Required dependency jq is not installed"
fi
```

## Trap Cleanup
Clean up temporary resources on exit:

```bash
CLEANUP_FILES=()

cleanup() {
    local exit_code=$?
    if [ ${#CLEANUP_FILES[@]} -gt 0 ]; then
        rm -rf "${CLEANUP_FILES[@]}"
    fi
    exit "$exit_code"
}
trap cleanup EXIT

# Register temporary files
tmpfile="$(mktemp)"
CLEANUP_FILES+=("$tmpfile")
```

## Argument Parsing with `getopt`
Use `getopt` for robust argument parsing:

```bash
parse_args() {
    local parsed
    parsed="$(getopt -o hv:o: --long help,verbose:,output: -n "$0" -- "$@")" || exit 1
    eval set -- "$parsed"

    while true; do
        case "$1" in
            -h|--help)    show_help; exit 0 ;;
            -v|--verbose) VERBOSE="$2"; shift 2 ;;
            -o|--output)  OUTPUT="$2"; shift 2 ;;
            --)           shift; break ;;
            *)            die "Internal error parsing arguments" ;;
        esac
    done

    readonly VERBOSE OUTPUT
}
```

## Additional Patterns
- Declare `readonly` for constants at the top of the script
- Use `local` inside functions to avoid leaking variables
- Prefer `[[ ]]` over `[ ]` for test expressions (fewer surprises)
- Use `${var:-default}` for safe defaults instead of testing with `if`
- Use shellcheck (`shellcheck script.sh`) for linting