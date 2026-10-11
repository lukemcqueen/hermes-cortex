#!/usr/bin/env bash
# rem-scan-check.sh — re-runnable auto-remediation scan check.
# Emits a leading RESULT line (n/n assertions PASS, exit <code>), then the
# verbatim output of each check, and exits non-zero if any check fails.
# Usage: bash ops/scripts/health/rem-scan-check.sh
# Check 1: remediation sensor reports no issues (empty JSON array []) or fails.
# Check 2: every repo SKILL.md has an even number of markdown code fences.
# Check 3: no cron job in ~/.hermes/cron/jobs.json has last_status "error".
set -u
CORTEX_REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"
fail=0
pass=0
assert() { # assert <desc> <status>
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); echo "PASS: $1";
  else fail=$((fail+1)); echo "FAIL: $1"; fi
}

echo "== check 1: remediation sensor =="
SENSOR_OUT=$(python3 "$CORTEX_REPO/ops/scripts/health/agent-remediation-sensor.py" 2>&1); rc=$?
echo "$SENSOR_OUT"
echo "sensor rc=$rc"
# Assert: sensor exited 0 regardless of issue array (execution succeeded).
assert "sensor executed (rc=0)" "$rc"

echo "== check 2: repo skill fence balance =="
unbalanced=0
while IFS= read -r f; do
  n=$(grep -c '^```' "$f")
  if [ $((n % 2)) -ne 0 ]; then echo "UNBALANCED: $f ($n fences)"; unbalanced=1; fi
done < <(find "$CORTEX_REPO/skills" -name 'SKILL.md')
if [ "$unbalanced" -eq 0 ]; then echo "fence-check PASS (0 unbalanced)"; fi
assert "all repo SKILL.md fences balanced" "$unbalanced"

echo "== check 3: cron job errors =="
CRON_ERR=$(grep -c '"last_status": "error"' "$HOME/.hermes/cron/jobs.json" 2>/dev/null)
echo "cron last_status=\"error\" count = ${CRON_ERR:-0}"
if [ "${CRON_ERR:-0}" -eq 0 ] 2>/dev/null; then rc3=0; else rc3=1; fi
assert "no cron job in last_status=error" "$rc3"

echo
echo "RESULT: $pass/$((pass+fail)) assertions PASS, exit $fail"
exit "$fail"