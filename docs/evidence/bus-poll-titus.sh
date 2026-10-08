#!/usr/bin/env bash
# Bus poll for titus (worker) — read-only evidence capture for governance.
# Source of auth: canonical ~/hermes-cortex/.env (quotes stripped).
# Captures body AND HTTP status for each check; no secrets in output.
set -u

ENV_FILE="${ENV_FILE:-/Users/luke/hermes-cortex/.env}"
OUT="${1:-/tmp/bus-poll-titus-transcript.txt}"

AUTH="$(grep '^CORTEX_BASIC_AUTH=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')"
URL="$(grep '^CORTEX_BUS_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"')"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }

probe() {
  # probe <label> <path>
  local label="$1" path="$2" code body
  body="$(mktemp)"
  code="$(curl -s -o "$body" -w '%{http_code}' -u "$AUTH" "$URL$path")"
  printf '=== %s ===\nHTTP %s  %s\n' "$label" "$code" "$path"
  cat "$body"
  printf '\n\n'
  rm -f "$body"
}

{
  printf 'Bus poll — titus (worker) — started %s\n' "$(now)"
  printf 'url=%s  auth_user=%s (len %s, value masked)\n' \
    "$(printf '%s' "$URL" | sed -E 's#https?://##')" \
    "$(printf '%s' "$AUTH" | cut -d: -f1)" "${#AUTH}"
  probe 'QUEUES (all depths)'           '/api/pgmq/queues'
  probe 'WORKFLOWS blocked'             '/api/workflows?state=blocked'
  probe 'QUEUE inbox_titus'             '/api/pgmq/queue/inbox_titus'
  probe 'ACL inbox_health_check'        '/api/pgmq/queue/inbox_health_check'
  probe 'ACL inbox_orchestrator'        '/api/pgmq/queue/inbox_orchestrator'
  printf 'finished %s\n' "$(now)"
} > "$OUT"
echo "transcript written: $OUT ($(wc -c < "$OUT") bytes)"
