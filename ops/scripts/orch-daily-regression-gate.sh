#!/usr/bin/env bash
# orch-daily-regression-gate.sh — F-008 daily golden regression gate.
#
# Runs the golden task suite (evals/suites/regression.yaml) against the live
# fleet invariants via run-evals.py. no_agent watchdog pattern:
#   - PASS  → empty stdout, exit 0  → silent, nothing delivered
#   - FAIL  → report on stdout, exit 1 → error alert delivered to Telegram
#
# Orchestrator-only. Deployed via register_orch in cortex-update.sh.
# Cron registered in install-orch-crons.sh (orch-daily-regression-gate).

set -uo pipefail

# Resolve the deployed harness (SOURCE header stripped on deploy; this path
# is the runtime copy, not the repo source).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_EVALS="${SCRIPT_DIR}/run-evals.py"

if [[ ! -f "${RUN_EVALS}" ]]; then
  echo "❌ orch-daily-regression-gate: run-evals.py not found at ${RUN_EVALS}"
  exit 1
fi

# 10-minute budget (spec F-008): the suite itself is fast (<30s when healthy);
# timeout catches a hung grader (e.g. bus unreachable) without blocking the
# scheduler. 570s leaves headroom under the 600s gateway cron limit.
OUTPUT="$(timeout 570 python3 "${RUN_EVALS}" --suite regression --standalone 2>&1)"
RC=$?

if [[ ${RC} -eq 0 ]]; then
  # PASS — silent watchdog behaviour: no stdout, exit 0.
  exit 0
fi

# FAIL — deliver the report as an error alert.
echo "❌ Daily regression gate FAILED (rc=${RC}) — $(date '+%Y-%m-%d %H:%M %Z')"
echo ""
echo "${OUTPUT}"
exit 1
