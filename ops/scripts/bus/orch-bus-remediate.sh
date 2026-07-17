#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-bus-remediate.sh — Read pending remediation markers
#
#  Reads state/remediate/ for pending fix requests left by
#  bus-sensor.py or bus-flag.py. Outputs structured JSON.
#
#  Output: JSON array. Empty [] when nothing pending (silent).
#
#  Called by agent-fixer cron (auto-remediation pipeline).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

STATE_DIR="${HOME}/.hermes-cortex/state"
REMEDIATE_DIR="${STATE_DIR}/remediate"
DONE_DIR="${REMEDIATE_DIR}/done"

mkdir -p "$DONE_DIR"

shopt -s nullglob
MARKERS=("${REMEDIATE_DIR}"/bus-*.txt "${REMEDIATE_DIR}"/inbox-*.txt)
shopt -u nullglob

if [ ${#MARKERS[@]} -eq 0 ]; then
  echo '[]'
  exit 0
fi

FIRST=true
echo '['
for marker in "${MARKERS[@]}"; do
  $FIRST || echo ','
  FIRST=false

  SENDER="$(grep '^from=' "$marker" 2>/dev/null | sed 's/^from=//')"
  SUBJECT="$(grep '^subject=' "$marker" 2>/dev/null | sed 's/^subject=//')"
  MSG_FILE="$(grep '^file=' "$marker" 2>/dev/null | sed 's/^file=//')"

  SENDER="${SENDER:-unknown}"
  SUBJECT="${SUBJECT:-No subject}"
  MSG_FILE="${MSG_FILE:-}"
  FILENAME=$(basename "$marker")

  echo '  {'
  echo "    \"sender\": $(echo "$SENDER" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),"
  echo "    \"subject\": $(echo "$SUBJECT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),"
  echo "    \"marker_file\": \"${marker}\","
  echo "    \"filename\": \"${FILENAME}\""
  echo '  }'
done
echo ']'
