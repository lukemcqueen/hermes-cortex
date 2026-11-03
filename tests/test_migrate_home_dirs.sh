#!/usr/bin/env bash
# Re-runnable test for ops/scripts/manage/migrate-home-dirs.sh (ADV-14085-1).
#
# Hermetic: runs the script against THROWAWAY dirs under a temp HOME via the
# `export HOME` env override — touches no real home. Covers the happy path
# (move, not copy; correct symlink targets), idempotency (re-run no-op), the
# unexpected-symlink guard (src->elsewhere must FAIL + name the target), the
# cwd-inside-source guard, and the missing-source no-op. Every run captures and
# asserts its exit code (errexit is OFF here, so a failing script cannot abort
# the harness). Run directly:  bash tests/test_migrate_home_dirs.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ops/scripts/manage/migrate-home-dirs.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check(){ if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fails=$((fails + 1)); fi; }

# 1. happy path: move (not copy) + correct symlink targets + content preserved
H="$TMP/h1"; rc=0
( export HOME="$H"; mkdir -p "$HOME/steadfaste-fleet/sub" "$HOME/.steadfaste-fleet/brain"
  echo m > "$HOME/steadfaste-fleet/marker"; echo y > "$HOME/.steadfaste-fleet/brain/a"
  cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ); rc=$?
check "happy migrate exits 0 (rc=$rc)" "[ '$rc' = '0' ]"
check "old paths are symlinks (moved, not copied)" "[ -L '$H/steadfaste-fleet' ] && [ -L '$H/.steadfaste-fleet' ]"
check "symlink targets resolve to new dirs" \
  "[ \"\$(readlink '$H/steadfaste-fleet')\" = '$H/steadfaste-fleet' ] && [ \"\$(readlink '$H/.steadfaste-fleet')\" = '$H/.steadfaste-fleet' ]"
check "new dirs exist" "[ -d '$H/steadfaste-fleet' ] && [ -d '$H/.steadfaste-fleet' ]"
check "content preserved (reachable through the symlink)" "[ -f '$H/steadfaste-fleet/marker' ] && [ -f '$H/.steadfaste-fleet/brain/a' ]"

# 2. idempotency: same fake home, re-run is a clean no-op
rc=0
( export HOME="$H"; cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ); rc=$?
check "idempotent re-run exits 0 (rc=$rc)" "[ '$rc' = '0' ]"
check "re-run left symlinks + new dirs intact" "[ -L '$H/steadfaste-fleet' ] && [ -d '$H/steadfaste-fleet' ]"

# 3. unexpected-symlink guard: ONE run; the exit code and the message come from
#    the SAME invocation.
H="$TMP/h2"; rc=0
( export HOME="$H"; mkdir -p "$HOME/elsewhere"
  ln -s "$HOME/elsewhere" "$HOME/steadfaste-fleet"
  cd "$HOME"; bash "$SCRIPT" >"$TMP/out2" 2>&1 ); rc=$?
check "unexpected-symlink guard exits non-zero (rc=$rc)" "[ '$rc' != '0' ]"
check "unexpected-symlink message names the target" "grep -q 'symlink to' '$TMP/out2'"

# 4. cwd-inside-source guard refuses with a non-zero exit
H="$TMP/h3"; rc=0
( export HOME="$H"; mkdir -p "$HOME/steadfaste-fleet"
  cd "$HOME/steadfaste-fleet"; bash "$SCRIPT" >"$TMP/out3" 2>&1 ); rc=$?
check "cwd-inside-source exits non-zero (rc=$rc)" "[ '$rc' != '0' ]"
check "cwd-inside-source message names the remedy" "grep -q 'stable workdir' '$TMP/out3'"

# 5. missing source is a clean no-op (exit 0, no new dir)
H="$TMP/h4"; rc=0
( export HOME="$H"; cd "$HOME"; bash "$SCRIPT" >/dev/null 2>&1 ); rc=$?
check "missing source exits 0 (rc=$rc)" "[ '$rc' = '0' ]"
check "missing source creates nothing" "[ ! -e '$H/steadfaste-fleet' ]"

if [ "$fails" -eq 0 ]; then echo "ALL PASS"; exit 0; else echo "FAILURES: $fails"; exit 1; fi
