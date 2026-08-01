#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-mycortex-sync.sh — mycortex knowledge brain sync (orch)
#
#  Cron: orch-mycortex-sync (install-orch-crons.sh), */15 * * * *
#
#  no_agent watchdog pattern:
#    Empty stdout + exit 0  → silent (nothing to report)
#    Error output + exit 1  → delivered as an error alert
#
#  Jittered per host (stable hostname-derived offset) so
#  multi-host syncs don't collide at the same minute. The
#  advisory lock inside mycortex sync() makes concurrent
#  syncs safe regardless.
#
#  Uses the deployed CLI — NEVER edit the deployed copy.
#  Source: ops/scripts/manage/orch-mycortex-sync.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail

CORTEX_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"
MYCORTEX="${CORTEX_HOME}/scripts/mycortex"

if [[ ! -x "$MYCORTEX" ]]; then
  echo "❌ orch-mycortex-sync: mycortex CLI not found at ${MYCORTEX} — run cortex-update.sh"
  exit 1
fi

# Per-host jitter: stable 0-120s offset derived from hostname
offset=$(( $(printf '%s' "$(hostname)" | cksum | awk '{print $1}') % 121 ))
sleep "$offset"

out="$("$MYCORTEX" sync 2>&1)"
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "❌ orch-mycortex-sync failed (rc=${rc}):"
  echo "$out"
  exit 1
fi

# Silent on success — sync is state, not a report
exit 0
