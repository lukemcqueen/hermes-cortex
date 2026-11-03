#!/usr/bin/env bash
# Re-runnable test for ops/scripts/manage/migrate-home-dirs.sh (ADV-14085-1).
#
# Hermetic: runs the script against THROWAWAY dirs under a temp HOME via the
# `export HOME` env override — touches no real home. Covers the happy path
# (rename + symlink), idempotency (re-run no-ops), the unexpected-symlink guard
# (src pointing elsewhere must fail + name the target), the cwd-inside-source
# guard, and the missing-source no-op. Run directly:  bash tests/test_migrate_home_dirs.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ops/scripts/manage/migrate-home-dirs.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check(){ if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fails=$((fails + 1)); fi; }
# the check condition string is double-quoted at the call site, so $VARS expand
# before eval; the inner single quotes are cosmetic and kept for clarity.

# 1. happy path
H="$TMP/h1"
( export HOME="$H"; mkdir -p "$HOME/hermes-cortex/sub" "$HOME/.hermes-cortex/brain"
  echo m > "$HOME/hermes-cortex/marker"; echo y > "$HOME/.hermes-cortex/brain/a"
  cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ) || true
check "happy path migrates both dirs" "[ -d '$H/steadfaste-fleet' ] && [ -d '$H/.steadfaste-fleet' ]"
check "happy path lays both symlinks" "[ -L '$H/hermes-cortex' ] && [ -L '$H/.hermes-cortex' ]"
check "content preserved" "[ -f '$H/steadfaste-fleet/marker' ] && [ -f '$H/.steadfaste-fleet/brain/a' ]"

# 2. idempotency (same fake home, re-run no-ops)
( export HOME="$H"; cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ) || true
check "idempotent re-run leaves symlinks + dirs intact" "[ -L '$H/hermes-cortex' ] && [ -d '$H/steadfaste-fleet' ]"

# 3. unexpected-symlink guard: ONE run; capture STDOUT/STDERR and the exit code
#    together so the failure that names the target is the same failure whose rc
#    we assert non-zero.
H="$TMP/h2"
( export HOME="$H"; mkdir -p "$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$HOME/hermes-cortex"
  cd "$HOME"; bash "$SCRIPT" >"$TMP/out2" 2>&1
  echo $? > "$TMP/rc2" ) || true
rc2=$(cat "$TMP/rc2")
check "unexpected-symlink guard exits non-zero (rc=$rc2)" "[ '$rc2' != '0' ]"
check "unexpected-symlink message names the target" "grep -q 'symlink to' '$TMP/out2'"

# 4. cwd-inside-source guard refuses
H="$TMP/h3"
( export HOME="$H"; mkdir -p "$HOME/hermes-cortex"
  cd "$HOME/hermes-cortex"; bash "$SCRIPT" >"$TMP/out3" 2>&1 ) || true
check "cwd-inside-source refused" "grep -q 'stable workdir' '$TMP/out3'"

# 5. missing source is a no-op
H="$TMP/h4"
( export HOME="$H"; cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ) || true
check "missing source no-ops cleanly" "[ ! -e '$H/steadfaste-fleet' ]"

if [ "$fails" -eq 0 ]; then echo "ALL PASS"; exit 0; else echo "FAILURES: $fails"; exit 1; fi
