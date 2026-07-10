#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  check-external-services.sh — verify external-facing services
#
#  Moses runs this at session start to detect service issues
#  that local tools would mask (MCP bypasses nginx).
#
#  Exit 0 = all healthy, 1 = any unhealthy
# ─────────────────────────────────────────────────────────────
set -euo pipefail

BASE="https://your-domain.com"
SERVICES=(
  "Main site:${BASE}/"
  "Dashboard:${BASE}:13001/"
  "Langfuse:${BASE}:13002/"
  "Inbox API:${BASE}:13004/health"
)

FAILED=0
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  url="${entry#*:}"
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
  if [[ "$status" == "000" ]]; then
    echo "❌ $name — connection refused (nginx down?)"
    FAILED=$((FAILED + 1))
  elif [[ "$status" == "401" ]]; then
    echo "✅ $name — 401 (nginx up, auth blocking as expected)"
  elif [[ "$status" == "200" ]] || [[ "$status" == "301" ]]; then
    echo "✅ $name — $status"
  else
    echo "⚠️  $name — $status (unexpected)"
  fi
done

echo ""
if [[ "$FAILED" -gt 0 ]]; then
  echo "❌ $FAILED service(s) unreachable"
  exit 1
else
  echo "✅ All external services reachable"
  exit 0
fi
