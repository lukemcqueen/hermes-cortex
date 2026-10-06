#!/usr/bin/env bash
# test-orch-skill-evaluate.sh — re-executable evidence for the
# orch-skill-evaluate inventory guards (2026-10-06 fix).
#
# Proves THREE behaviors of ops/scripts/manage/orch-skill-evaluate.sh:
#   1. normal run enumerates the real skills tree (count > 0)
#   2. a MISSING skills root exits 1 with an ERROR (fail-closed)
#   3. an UNREADABLE subdir produces a find-error WARN (stderr captured
#      via temp file — the subshell capture that silently no-op'd is fixed)
#
# Usage: bash test-orch-skill-evaluate.sh
# Exit 0 = all assertions passed; non-zero = a behavior regressed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || true)")" && pwd)"
TARGET="${SCRIPT_DIR}/orch-skill-evaluate.sh"
[[ -f "$TARGET" ]] || { echo "FAIL: $TARGET not found"; exit 2; }

PASS=0; FAIL=0
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "== 1. syntax =="
if bash -n "$TARGET"; then ok "bash -n clean"; else bad "bash -n failed"; fi

echo "== 2. normal run enumerates skills (count > 0) =="
OUT="$(bash "$TARGET" 2>&1)"
CNT="$(printf '%s\n' "$OUT" | sed -n 's/^Total skills: *//p' | head -1)"
if [[ "${CNT:-0}" -gt 0 ]]; then ok "Total skills: $CNT"; else bad "Total skills not > 0 (got '${CNT:-<none>}')"; fi

echo "== 3. missing skills root fails closed =="
TBAD="$(mktemp -d)"
RC=0
OUT="$(HOME="$TBAD/nonexistent" bash "$TARGET" 2>&1)" || RC=$?
if [[ "$RC" -ne 0 ]] && grep -q "ERROR: skills root not found" <<<"$OUT"; then
  ok "missing root -> exit $RC + ERROR"
else
  bad "missing root did not fail closed (rc=$RC)"
fi
rm -rf "$TBAD"

echo "== 4. unreadable subdir emits find-error WARN =="
# Build an isolated skills root with one unreadable subdir. Drive the
# inventory portion directly (bus phase will warn 401 — that is not this test).
TROOT="$(mktemp -d)"
mkdir -p "$TROOT/sub"
: > "$TROOT/sub/SKILL.md"
chmod 000 "$TROOT/sub"
# Run with SKILLS_ROOT overridden via a sed-patched copy (the script derives
# SKILLS_ROOT from $HOME, so point HOME at our temp root).
mkdir -p "$TROOT/.hermes/skills/sub"
: > "$TROOT/.hermes/skills/sub/SKILL.md"
chmod 000 "$TROOT/.hermes/skills/sub"
OUT="$(HOME="$TROOT" bash "$TARGET" 2>&1)"
chmod -R 755 "$TROOT" 2>/dev/null || true
if grep -q "WARN: find reported errors" <<<"$OUT"; then
  ok "unreadable subdir -> find-error WARN"
else
  bad "unreadable subdir produced no WARN (stderr capture broken?)"
fi
rm -rf "$TROOT"

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
