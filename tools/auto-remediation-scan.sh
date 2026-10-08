#!/usr/bin/env bash
# Runnable auto-remediation scan — emits verifiable summary output for the
# remediate-scan governance close-out. Read-only: never writes state.
# Usage: bash tools/auto-remediation-scan.sh
set -euo pipefail
CORTEX_REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"
JOBS_FILE="${JOBS_FILE:-$HOME/.hermes/cron/jobs.json}"
SENSOR_SCRIPT="${SENSOR_SCRIPT:-$HOME/.hermes-cortex/scripts/agent-remediation-sensor.py}"
FAIL=0

echo "== FENCE BALANCE =="
if [ ! -d "$CORTEX_REPO/skills" ]; then
  echo "ERROR: skills dir not found at $CORTEX_REPO/skills"; FAIL=1
else
  FILES=$(find "$CORTEX_REPO/skills" -name 'SKILL.md' | wc -l | tr -d ' ')
  UNBAL=0
  while read -r f; do
    n=$(grep -c '^```' "$f" || true)
    if [ $((n % 2)) -ne 0 ]; then
      echo "  UNBALANCED: $f ($n fences)"; UNBAL=1; FAIL=1
    fi
  done < <(find "$CORTEX_REPO/skills" -name 'SKILL.md')
  echo "FILES_SCANNED=$FILES UNBALANCED_TOTAL=$UNBAL"
fi

echo "== CRON STATUS =="
if [ ! -f "$JOBS_FILE" ]; then
  echo "ERROR: jobs.json not found at $JOBS_FILE"; FAIL=1
else
  python3 - "$JOBS_FILE" <<'PY' || { echo "ERROR: cron-status scan failed"; FAIL=1; }
import json, sys
d = json.load(open(sys.argv[1]))
jobs = d if isinstance(d, list) else d.get('jobs', d)
jobs = jobs if isinstance(jobs, list) else list(jobs.values())
total = 0; missed = 0
for j in jobs:
    if not isinstance(j, dict): continue
    total += 1
    st = j.get('last_status')
    if st and st != 'ok':
        missed += 1
        print(f"  NOT-OK {j.get('name','?')}: {st}")
print(f"TOTAL_JOBS={total} NOT_OK={missed} (all-ok={1 if missed==0 else 0})")
PY
fi

echo "== SENSOR =="
if [ ! -f "$SENSOR_SCRIPT" ]; then
  echo "ERROR: sensor not found at $SENSOR_SCRIPT"; FAIL=1
else
  OUT=$(python3 "$SENSOR_SCRIPT" 2>&1) || { echo "ERROR: sensor failed: $OUT"; FAIL=1; }
  echo "$OUT"
  echo "SENSOR_EXIT=0"
fi

echo "== DISK =="
df -h / | tail -1

echo "== RESULT =="
if [ "$FAIL" -eq 0 ]; then
  echo "ALL_HEALTHY=1"
else
  echo "ALL_HEALTHY=0"; exit 1
fi