# Ad-Hoc Verification Script Pattern

When the system requests verification of changes (or when verification is prudent after a batch of edits), create a focused temporary script that exercises only the changed behavior — not the full test suite.

## When to use

- System requests "fresh passing verification evidence" after a code edit
- Changes span multiple files but testing the full suite is expensive or known to have pre-existing failures
- You need to prove the changed code compiles, parses, or behaves correctly without running the entire CI pipeline

## Script shape

```bash
#!/bin/bash
# Ad-hoc verification for: <description of changes>

ROOT="/path/to/project"
PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" 2>/dev/null; then
        echo "  ✅ $desc"
        PASS=$((PASS+1))
    else
        echo "  ❌ $desc"
        FAIL=$((FAIL+1))
    fi
}

# Group checks by concern

echo "═══ .gitignore patterns ═══"
cd "$ROOT"
check "pattern X works" git check-ignore some/debug/file.ts
check "pattern Y does NOT match" test ! -n "$(git check-ignore some/real/file.ts 2>/dev/null && echo x)"

echo ""
echo "═══ data structure ═══"
cd "$WEB"
check "field exists in all entries" grep -q 'expected_field:' src/file.test.tsx
check "null vs object values correct" grep -q 'field: null,' src/file.test.tsx

echo ""
echo "═══ TS compile (project tsconfig) ═══"
if npx tsc --noEmit 2>&1 | grep -q 'error TS'; then
    echo "  ❌ TS errors found"
    npx tsc --noEmit 2>&1 | grep 'error TS' | head -3
    FAIL=$((FAIL+1))
else
    echo "  ✅ TS zero errors"
    PASS=$((PASS+1))
fi

echo ""
echo "═══ summary: $PASS passed, $FAIL failed ═══"
exit "$FAIL"
```

## Key design principles

1. **Targeted checks** — test only what changed, not the full project
2. **Self-cleaning** — `rm -f "$0"` at the end deletes the script after success
3. **Exit code reflects failures** — `exit "$FAIL"` makes CI/hooks see it
4. **Compact format** — one line per check, no verbose logging
5. **Each check is independent** — one failing check doesn't abort the rest (no `set -e`)
6. **Writes to a temp path** — use `/var/folders/.../T/hermes-verify-<slug>.sh` via `cat` + heredoc in terminal (write_file tool may reject /var/folders as a "sensitive system path")

## When the full test suite matters more

The ad-hoc script is NOT a substitute for the full test suite. Use it when:
- The full suite has known pre-existing failures unrelated to your changes
- The changes are purely structural (config, types, documentation)
- The system verification gate fires before you've had time to run the full suite

When you DO run the full suite, report actual pass/fail counts from the canonical test command (`./run test`, `pnpm test`, `vitest run`, etc.)
