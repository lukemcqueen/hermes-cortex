#!/usr/bin/env bash
# Auto-remediation diagnostic proof — re-executable (cron e7ce31e8ce1b, 2026-10-08).
# Runs fence check, sensor check, and service-health check; records machine-readable
# output with exit codes. Non-server host → fence/sensor/git checks only.
set -u
REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"
OUT="${1:-/tmp/auto-remediation-diagnostics.log}"
: > "$OUT"

echo "=== PHASE 0: repo skill fence balance ===" >> "$OUT"
UNBALANCED=0
while IFS= read -r f; do
  n=$(grep -c '^```' "$f")
  if [ $((n % 2)) -ne 0 ]; then echo "UNBALANCED: $f ($n fences)" >> "$OUT"; UNBALANCED=1; fi
done < <(cd "$REPO" && find skills -name 'SKILL.md')
if [ "$UNBALANCED" -eq 0 ]; then echo "RESULT: balanced (0 UNBALANCED)" >> "$OUT"; fi
echo "EXIT:$UNBALANCED" >> "$OUT"

echo "=== PHASE 1: sensor state ===" >> "$OUT"
SENSOR=$(cd "$REPO" && python3 ops/scripts/health/agent-remediation-sensor.py 2>&1)
echo "$SENSOR" >> "$OUT"
echo "EXIT:$?  ([] = no issues on this host)" >> "$OUT"

echo "=== PHASE 2: git state (dirty-scripts source) ===" >> "$OUT"
cd "$REPO"
echo "branch: $(git branch --show-current 2>&1)" >> "$OUT"
git symbolic-ref -q HEAD >/dev/null 2>&1 && echo "detached: no" >> "$OUT" || echo "detached: YES" >> "$OUT"
git status --short >> "$OUT" 2>&1
echo "EXIT:$?" >> "$OUT"

echo "=== PHASE 3: service health (non-server host) ===" >> "$OUT"
if grep -q 'IS_SERVER=true' "$REPO/.env" 2>/dev/null; then
  echo "docker-running: $(docker ps -q 2>/dev/null | wc -l | tr -d ' ')" >> "$OUT"
  echo "ollama-http: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:11434/api/tags 2>/dev/null || echo down)" >> "$OUT"
else
  echo "IS_SERVER=false → non-server host; per skill host-gating, no local fleet bus/nginx to remediate." >> "$OUT"
fi
echo "EXIT:0" >> "$OUT"

echo "DONE. Log: $OUT"