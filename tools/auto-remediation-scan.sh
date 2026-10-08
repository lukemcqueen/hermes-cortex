#!/usr/bin/env bash
# Runnable auto-remediation scan — emits raw, verifiable output for the 
# remediate-scan governance close-out. Read-only: never writes state.
# Usage: bash ops/scripts/manage/auto-remediation-scan.sh
set -u
CORTEX_REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"

echo "== FENCE BALANCE =="
unbal=0
while read -r f; do
  n=$(grep -c '^```' "$f")
  echo "$n fences: $f"
  if [ $((n % 2)) -ne 0 ]; then unbal=1; echo "  ^ UNBALANCED"; fi
done < <(find "$CORTEX_REPO/skills" -name 'SKILL.md')
echo "UNBALANCED_TOTAL=$unbal"

echo "== CRON STATUS =="
python3 - "$HOME/.hermes/cron/jobs.json" <<'PY'
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

echo "== SENSOR =="
python3 "$HOME/.hermes-cortex/scripts/agent-remediation-sensor.py" 2>&1
echo "SENSOR_EXIT=$?"

echo "== DISK =="
df -h / | tail -1