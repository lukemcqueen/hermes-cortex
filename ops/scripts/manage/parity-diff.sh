#!/usr/bin/env bash
# parity-diff.sh — daily mycortex parity gate watchdog (S-010 / P2-SS9)
#
# Runs the golden parity check against the deployed mycortex CLI.
# SILENT when the gate passes (watchdog pattern — no news is good news).
# Prints the failure summary + rates when the gate regresses, so the
# cron delivery path alerts the fleet owner.
#
# Used by the daily 'local-mycortex-parity' cron (no_agent mode).
set -u

REPO="${HOME}/hermes-cortex"
PARITY="${REPO}/ops/scripts/manage/mycortex-parity.py"
CLI="${HOME}/.hermes-cortex/scripts/mycortex"

# Hosts without mycortex deployed: nothing to gate, stay silent.
if [ ! -x "${CLI}" ] || [ ! -f "${PARITY}" ]; then
  exit 0
fi

export PATH="${HOME}/.hermes-cortex/scripts:${PATH}"

# Hosts without any registered source: nothing to gate, stay silent.
SOURCES=$("${CLI}" sources list --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo 0)
if [ "${SOURCES}" = "0" ]; then
  exit 0
fi

OUT=$(python3 "${PARITY}" --mode check --engine mycortex 2>&1)
RC=$?

if [ "${RC}" -eq 0 ]; then
  # Gate passed — watchdog stays silent (no output = no delivery).
  exit 0
fi

# Gate FAILED — emit the summary so the cron delivery alerts the owner.
echo "❌ mycortex parity gate REGRESSION (exit ${RC})"
echo "${OUT}" | tail -8
echo "Fix before the gbrain flip gate: run mycortex-parity.py --mode check --engine mycortex"
exit 0
