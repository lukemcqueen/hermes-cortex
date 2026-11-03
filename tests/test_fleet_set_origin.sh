#!/usr/bin/env bash
# Re-runnable test for ops/scripts/manage/fleet-set-origin.sh (ADV-14072-1).
#
# Drives the script's five branches against THROWAWAY git repos in a temp dir
# via the FLEET_SET_ORIGIN_REPO env override, asserting the resulting
# remote.origin.url and exit code. No shared state is touched. Run directly:
#   bash tests/test_fleet_set_origin.sh
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ops/scripts/manage/fleet-set-origin.sh"
LEGACY="https://github.com/lukemcqueen/hermes-cortex.git"
CANONICAL="https://github.com/lukemcqueen/steadfaste-fleet.git"
UNEXPECTED="https://github.com/other/thing.git"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { # name, cond-string
  if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fails=$((fails + 1)); fi
}
new_repo() { mkdir -p "$TMP/$1" && (cd "$TMP/$1" && git init -q); }
url_of() { git -C "$TMP/$1" config --get remote.origin.url 2>/dev/null || true; }

# 1. not a git repo  -> non-zero
set +e; FLEET_SET_ORIGIN_REPO="$TMP/nonexistent" "$SCRIPT" >/dev/null 2>&1; rc=$?; set -e
check "no-git-repo exits non-zero" "[ $rc -ne 0 ]"

# 2. git repo, no origin -> adds canonical
new_repo norigin
set +e; FLEET_SET_ORIGIN_REPO="$TMP/norigin" "$SCRIPT" >/dev/null 2>&1; rc=$?; set -e
check "no-origin exit 0" "[ $rc -eq 0 ]"
check "no-origin sets canonical" "[ \"$(url_of norigin)\" = \"$CANONICAL\" ]"

# 3. legacy origin -> repointed to canonical
new_repo legacy
(cd "$TMP/legacy" && git remote add origin "$LEGACY")
set +e; FLEET_SET_ORIGIN_REPO="$TMP/legacy" "$SCRIPT" >/dev/null 2>&1; rc=$?; set -e
check "legacy exit 0" "[ $rc -eq 0 ]"
check "legacy -> canonical" "[ \"$(url_of legacy)\" = \"$CANONICAL\" ]"

# 4. canonical origin -> idempotent no-op
new_repo canonical
(cd "$TMP/canonical" && git remote add origin "$CANONICAL")
set +e; FLEET_SET_ORIGIN_REPO="$TMP/canonical" "$SCRIPT" >/dev/null 2>&1; rc=$?; set -e
check "canonical exit 0" "[ $rc -eq 0 ]"
check "canonical unchanged" "[ \"$(url_of canonical)\" = \"$CANONICAL\" ]"

# 5. unexpected origin -> left untouched, exit 0
new_repo unexpected
(cd "$TMP/unexpected" && git remote add origin "$UNEXPECTED")
set +e; FLEET_SET_ORIGIN_REPO="$TMP/unexpected" "$SCRIPT" >/dev/null 2>&1; rc=$?; set -e
check "unexpected exit 0" "[ $rc -eq 0 ]"
check "unexpected left unchanged" "[ \"$(url_of unexpected)\" = \"$UNEXPECTED\" ]"

if [ "$fails" -eq 0 ]; then echo "ALL PASS"; exit 0; else echo "FAILURES: $fails"; exit 1; fi
