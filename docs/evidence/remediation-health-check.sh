#!/usr/bin/env bash
# Auto-remediation health check — 2026-10-08 (evidence for remediate-auto-scan).
# Re-executable: runs the sensor + spot checks, echoes EVERYTHING (unmodified),
# exits 0 only if the sensor is empty. Committed under docs/evidence/ because
# tests/ and ops/scripts/ are orchestrator-only paths on this host.
set -u
REPO="${HOME}/hermes-cortex"
SENSOR="${REPO}/ops/scripts/health/agent-remediation-sensor.py"

echo "=== sensor ==="
python3 "${SENSOR}"
echo "=== sensor_exit=${?} ==="

echo "=== disk (df -h / | tail -1) ==="
df -h / | tail -1

echo "=== ollama (curl status) ==="
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:11434/api/tags

echo "=== bus (curl status; CORTEX_BUS_URL from .env) ==="
BUS_URL=$(grep -E '^CORTEX_BUS_URL=' "${REPO}/.env" | head -1 | cut -d= -f2- | tr -d '"')
if [ -n "${BUS_URL}" ]; then
  curl -s -k -o /dev/null -w '%{http_code}\n' "${BUS_URL}/health"
else
  echo "CORTEX_BUS_URL not set"
fi

echo "=== fences ==="
cd "${REPO}"
UNB=0
for f in $(find skills -name 'SKILL.md'); do
  n=$(grep -c '^```' "$f")
  if [ $((n % 2)) -ne 0 ]; then echo "UNBALANCED: $f ($n)"; UNB=1; fi
done
[ $UNB -eq 0 ] && echo "balanced"
echo "=== done ==="

# Exit 0 iff sensor empty and no unfixed issues detected.
sensor_out=$(python3 "${SENSOR}" 2>/dev/null)
if [ "$sensor_out" = "[]" ] && [ $UNB -eq 0 ]; then
  echo "RESULT: PASS (sensor empty, fences balanced)"
  exit 0
else
  echo "RESULT: FAIL"
  exit 1
fi