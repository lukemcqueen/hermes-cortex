# Shell Script Verification — Reproduction Recipe

Use when fixing shell scripts with `set -euo pipefail` — typically no_agent cron
jobs or orchestration scripts. The AST-based Python verification approach
doesn't apply to shell; use this recipe instead.

## Template

```bash
#!/usr/bin/env bash
# Ad-hoc verification: <script-name> — <what was fixed>
set -euo pipefail

SCRIPT_PATH="$HOME/.hermes/scripts/<script-name>"
REPO_PATH="$HOME/hermes-cortex/ops/scripts/manage/<script-name>"
PASS=0; FAIL=0

verify() {
    local path="$1" label="$2"

    # 1. Structural: guard pattern exists in file
    if grep -q '<unique-pattern>' "$path"; then
        echo "  [PASS] Guard pattern found"; PASS=$((PASS+1))
    else
        echo "  [FAIL] Guard pattern missing"; FAIL=$((FAIL+1))
    fi

    # 2. Syntax: bash -n validates parse tree
    if bash -n "$path" 2>/dev/null; then
        echo "  [PASS] Shell syntax valid"; PASS=$((PASS+1))
    else
        echo "  [FAIL] Shell syntax error"; FAIL=$((FAIL+1))
    fi

    # 3. Runtime: test the degraded path (missing dependency)
    output=$(URL="" bash "$path" 2>&1) || true
    code=$?
    if [[ $code -eq 0 && -z "$output" ]]; then
        echo "  [PASS] Silent exit 0 (degraded path)"; PASS=$((PASS+1))
    else
        echo "  [FAIL] code=$code output='$output'"; FAIL=$((FAIL+1))
    fi
}

verify "$SCRIPT_PATH" "Deployed copy"
verify "$REPO_PATH" "Repo source"

echo -e "\n$PASS pass, $FAIL fail"
[[ $FAIL -eq 0 ]] || exit 1
```

## Key techniques

| Technique | Purpose | Example |
|-----------|---------|---------|
| `bash -n` | Parse validation without executing | `bash -n script.sh` |
| Env injection | Test code paths without touching config | `VAR=value bash script.sh` |
| `2>&1` capture | Assert no stderr noise on degraded path | `output=$(VAR=X bash script.sh 2>&1)` |
| `set -euo pipefail` guard | Reveal unhandled errors in the test itself | Add at top of verification script |
| grep pattern assertion | Structural proof that guard exists | `grep -q 'pattern' "$path"` |

## Cleanup

`rm /tmp/hermes-verify-*.sh` — if security policy blocks the delete, leave it.
`/tmp` is cleared on reboot and the files are owned by the user, not world-writable.
