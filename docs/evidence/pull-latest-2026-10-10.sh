#!/usr/bin/env bash
# Evidence for governance cycle pull-latest-hc-update-cortex (2026-10-10).
# Asserts (exit non-zero on any mismatch):
#   1. Upstream has nothing new (0 behind; local may be ahead)
#   2. cortex-update deployed HEAD (state/update-commit == git rev-parse HEAD)
#   3. Repo-local ~/hermes-cortex/.hermes-cortex is absent
#   4. Doctor's ONLY FAIL is AGENTS.md (steadfaste) — pre-existing issue #57
set -uo pipefail
REPO="${HOME}/hermes-cortex"
FAILS=0
ok()   { echo "PASS: $1"; }
bad()  { echo "FAIL: $1"; FAILS=$((FAILS+1)); }

echo "=== 1. UPSTREAM STATE ==="
git -C "$REPO" fetch origin 2>&1 || bad "git fetch failed"
read -r AHEAD BEHIND < <(git -C "$REPO" rev-list --left-right --count HEAD...@{u})
echo "ahead=$AHEAD behind=$BEHIND"
[ "$BEHIND" = "0" ] && ok "behind=0 (nothing new to pull)" || bad "behind=$BEHIND, expected 0"
NEW_UPSTREAM=$(git -C "$REPO" log --oneline HEAD..@{u})
[ -z "$NEW_UPSTREAM" ] && ok "HEAD..@{u} empty" || bad "new upstream commits exist: $NEW_UPSTREAM"

echo
echo "=== 2. DEPLOY SYNC ==="
DEPLOYED=$(cat "${HOME}/.hermes-cortex/state/update-commit")
HEAD_SHA=$(git -C "$REPO" rev-parse HEAD)
echo "deployed=$DEPLOYED head=$HEAD_SHA"
[ "$DEPLOYED" = "$HEAD_SHA" ] && ok "update-commit == HEAD" || bad "deploy != HEAD ($DEPLOYED != $HEAD_SHA)"

echo
echo "=== 3. REPO-LOCAL .hermes-cortex ABSENT ==="
if [ -e "$REPO/.hermes-cortex" ]; then
  bad "repo-local .hermes-cortex still present"
else
  ok "repo-local .hermes-cortex absent"
fi

echo
echo "=== 4. DOCTOR FAIL SET ==="
DOCTOR_OUT=$(python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet 2>&1)
DOCTOR_RC=$?
echo "doctor exit code: $DOCTOR_RC"
if [ -z "$DOCTOR_OUT" ]; then
  bad "doctor produced EMPTY output (did not run or crashed silently)"
else
  echo "$DOCTOR_OUT" | grep -E "❌|⚠️|Overall" || true
  # The doctor must actually report the expected steady state: the only FAIL
  # is the pre-existing AGENTS.md (steadfaste). Require that line to be present
  # so an empty/absent run cannot pass.
  echo "$DOCTOR_OUT" | grep -q "❌ AGENTS.md (steadfaste)" && ok "doctor reports expected AGENTS.md (steadfaste) FAIL" || bad "doctor did not report the expected AGENTS.md (steadfaste) FAIL line"
  echo "$DOCTOR_OUT" | grep -q "❌ Overall:" && ok "doctor Overall verdict present" || bad "doctor Overall verdict line missing"
  FAILS_LINE=$(echo "$DOCTOR_OUT" | grep "❌ " | grep -vE "AGENTS.md \(steadfaste\)|Overall:|REQUIRED ACTIONS" || true)
  [ -z "$FAILS_LINE" ] && ok "no FAILs other than AGENTS.md (steadfaste)" || bad "unexpected FAIL(s): $FAILS_LINE"
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "RESULT: ALL CHECKS PASSED"
  exit 0
else
  echo "RESULT: $FAILS CHECK(S) FAILED"
  exit 1
fi
