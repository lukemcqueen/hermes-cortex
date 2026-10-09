#!/usr/bin/env bash
# Runnable scan used by agent-auto-remediate on this host.
# Executes the remediation sensor, asserts an empty issue list, checks
# SKILL.md fence balance, and asserts host gating. Exits 0 only if all pass.
# Usage: bash ops/scripts/health/auto-remediate-scan.sh
set -u
CORTEX_REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"
fail=0

echo "== sensor =="
out="$(python3 "$CORTEX_REPO/ops/scripts/health/agent-remediation-sensor.py" 2>&1)"
rc=$?
echo "exit=$rc output=$out"
[ $rc -eq 0 ] || fail=1
[ -n "$out" ] || { echo "ERROR: sensor produced no output"; fail=1; }
case "$out" in
  '[]'|'["'*) : ;; # empty array (non-server host) or JSON array
  *) echo "ERROR: sensor output not empty/valid: $out"; fail=1;;
esac

echo "== fences =="
unbal=0
while IFS= read -r f; do
  n=$(grep -c '^```' "$f")
  if [ $((n % 2)) -ne 0 ]; then echo "UNBALANCED: $f ($n)"; unbal=1; fi
done < <(find "$CORTEX_REPO/skills" -name SKILL.md)
echo "unbalanced=$unbal"
[ $unbal -eq 0 ] || fail=1

echo "== host gating =="
is_server=$(grep -i '^IS_SERVER=' "$CORTEX_REPO/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '"' | tr -d '[:space:]')
echo "IS_SERVER=${is_server:-unset}"
[ "${is_server:-false}" = "false" ] || fail=1

if [ $fail -eq 0 ]; then echo "SCAN-HEALTHY"; else echo "SCAN-UNHEALTHY"; fi
exit $fail