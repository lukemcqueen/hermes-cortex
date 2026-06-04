---
name: bash-shell
description: |
  Write, refactor, and validate safe, portable shell scripts for automation,
  dev tooling, CI, and local system tasks.

  Triggers when user mentions:
  - "bash"
  - "shell script"
  - "script this"
  - "cli automation"
  - "terminal command"
---

# Bash / Shell

## Purpose
Create shell scripts that are safe, predictable, portable, and debuggable.

Use for:
- bash scripts
- shell automation
- local tooling
- CI helper scripts
- install/validation scripts

---

## Core Rule
Never run or generate destructive commands without explicit intent and safeguards.

---

## Output (STRICT ORDER)
1. **Script**
2. **Explanation** (≤3 sentences)
3. **Verification**

---

## Safety Defaults
For bash scripts, start with:

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
```

Rules:
- fail on errors
- fail on unset variables
- fail on pipe errors
- quote variables
- validate inputs

---

## Path Safety
Always quote variables:

```bash
"$FILE"
```

Avoid:

```bash
rm -rf $DIR
```

Prefer guarded destructive operations:

```bash
if [ -n "${DIR:-}" ] && [ -d "$DIR" ]; then
  rm -rf -- "$DIR"
fi
```

---

## Input Validation
Validate required inputs:

```bash
if [ -z "${PROJECT_ROOT:-}" ]; then
  echo "PROJECT_ROOT is required" >&2
  exit 1
fi
```

Check required commands:

```bash
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
```

---

## Idempotency
Scripts should be safe to run multiple times.

```bash
mkdir -p "$DIR"
```

Avoid relying on hidden prior state.

---

## Temporary Files
Use `mktemp` and cleanup traps:

```bash
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT
```

---

## Logging
Use clear logs:

```bash
echo "[INFO] Starting validation"
echo "[ERROR] Missing config" >&2
```

Do not log secrets.

---

## Portability
- prefer POSIX-compatible syntax when possible
- use bash-specific features only when needed
- avoid hardcoded absolute paths
- resolve paths relative to repo root

---

## Dangerous Commands (RESTRICTED)
Require explicit approval or strong guards:

- `rm -rf`
- `chmod -R`
- `chown -R`
- `kill -9`
- `dd`
- disk/volume operations
- production deploy/destructive commands

---

## Verification
Run the narrowest safe check first:

```bash
bash -n script.sh
shellcheck script.sh
./script.sh --help
```

Use `shellcheck` if available.

---

## Anti-Patterns
Avoid:
- unquoted variables
- silent failures
- destructive defaults
- hardcoded machine paths
- assuming tools are installed
- ignoring exit codes
- storing secrets in scripts

---

## Final Report
```md
## Result
What changed.

## Files changed
- path: purpose

## Verification
- command: result

## Notes
Risks, portability limits, follow-ups.
```

---

## Goal
Produce safe, reliable shell scripts that behave consistently and do not damage user environments.
