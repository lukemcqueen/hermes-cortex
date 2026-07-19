#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  agent-gbrain-doctor.sh — Daily gbrain brain health check
#
#  no_agent watchdog pattern:
#    Empty stdout → silent (all healthy)
#    Text output  → delivered (issues found)
#
#  Pauses the gbrain autopilot via gbrain-wrapper.sh, runs
#  gbrain doctor --json, checks for source/sync failures,
#  and restarts autopilot. Only produces output when issues
#  are found (watchdog quiet pattern).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

WRAPPER="${HOME}/.hermes-cortex/scripts/gbrain-wrapper.sh"
GBRAIN_BIN="$(command -v gbrain || echo "${HOME}/.bun/bin/gbrain")"

if [ ! -x "$GBRAIN_BIN" ]; then
  echo "❌ gbrain not found — skipping daily doctor check"
  exit 0
fi

if [ ! -f "$WRAPPER" ]; then
  # Fallback: run directly with manual stop/start
  systemctl --user stop gbrain-autopilot.service 2>/dev/null || true
  sleep 1
  OUT=$("$GBRAIN_BIN" doctor --json 2>/dev/null || echo "")
  systemctl --user start gbrain-autopilot.service 2>/dev/null || true
else
  OUT=$(bash "$WRAPPER" "$GBRAIN_BIN" doctor --json 2>/dev/null || echo "")
fi

if [ -z "$OUT" ]; then
  exit 0  # silent — no result to report
fi

# Parse for failures
FAILURES=$(echo "$OUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, SystemExit):
    sys.exit(1)
checks = data.get('doctor', {}).get('checks', [])
failures = []
for c in checks:
    name = c.get('name', '')
    status = c.get('status', '')
    msg = c.get('message', '')[:120]
    if status == 'fail' and any(kw in name for kw in ['sync', 'source']):
        failures.append(f'  ❌ {name}: {msg}')
    elif status == 'warn' and name in ('sync_freshness',):
        failures.append(f'  ⚠ {name}: {msg}')
# Also check sync freshness for never-synced sources
sync_checks = [c for c in checks if c.get('name') == 'sync_freshness']
if sync_checks:
    sync_msg = sync_checks[0].get('message', '')
    if 'never' in sync_msg.lower() or '0 page' in sync_msg.lower():
        failures.append(f'  ⚠ Sources never synced or have 0 pages')
overall = data.get('overall_health_score', -1)
if failures:
    print(f'━━━ gbrain Brain Health ━━━')
    print(f'  Score: {overall}/100')
    for f in failures:
        print(f)
elif 0 <= overall < 50:
    print(f'━━━ gbrain Brain Health ━━━')
    print(f'  Score: {overall}/100 (low, but no hard failures)')
" 2>/dev/null) || true

if [ -n "$FAILURES" ]; then
  echo "$FAILURES"
fi
exit 0
