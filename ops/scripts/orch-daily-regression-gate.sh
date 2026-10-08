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
# run-evals.py relocated to ops/scripts/manage/ (commit 0e5be574) — resolve robustly.
if [[ ! -f "${RUN_EVALS}" ]]; then
  RUN_EVALS="${SCRIPT_DIR}/manage/run-evals.py"
fi

if [[ ! -f "${RUN_EVALS}" ]]; then
  echo "❌ orch-daily-regression-gate: run-evals.py not found at ${RUN_EVALS}"
  exit 1
fi

# 10-minute budget (spec F-008): the suite itself is fast (<30s when healthy);
# timeout catches a hung grader (e.g. bus unreachable) without blocking the
# scheduler. 570s leaves headroom under the 600s gateway cron limit.
#
# Resolve an interpreter that can actually IMPORT PyYAML. Testing a PATH is not a test:
# ~/.hermes-cortex/venv/bin/python3 EXISTS on this host but imports no yaml, so this
# gate's previous guard (`if [[ ! -x $PY ]]`) never fired, the eval harness ran under a
# PyYAML-less python, and the gate failed EVERY DAY with "PyYAML is not installed —
# cannot parse eval definitions". A comment claiming "the cortex venv has PyYAML" is not
# a guard. The resolver tests the CAPABILITY and refuses loudly when none has it.
PY_HELPER="${SCRIPT_DIR}/lib/python-with-module.sh"
if [[ ! -f "${PY_HELPER}" ]]; then
  PY_HELPER="${SCRIPT_DIR}/python-with-module.sh"
fi
if [[ ! -f "${PY_HELPER}" ]]; then
  echo "⚠️ orch-daily-regression-gate COULD NOT VERIFY — python-with-module.sh not found beside this script (${SCRIPT_DIR}); the suite did NOT run."
  exit 3
fi

OUTPUT="$(timeout 570 bash "${PY_HELPER}" yaml "${RUN_EVALS}" --suite regression --standalone 2>&1)"
RC=$?

# rc=3 is the resolver's "no interpreter can import PyYAML" — a third outcome, distinct
# from a suite that ran and failed. Reporting it as a failed suite would blame the
# golden tasks for the host's missing dependency.
if [[ ${RC} -eq 3 ]]; then
  echo "⚠️ Daily regression gate COULD NOT VERIFY (rc=3) — the suite did NOT run."
  echo ""
  echo "${OUTPUT}"
  exit 3
fi

if [[ ${RC} -eq 0 ]]; then
  # PASS — silent watchdog behaviour: no stdout, exit 0.
  exit 0
fi

# FAIL — deliver the report as an error alert.
echo "❌ Daily regression gate FAILED (rc=${RC}) — $(date '+%Y-%m-%d %H:%M %Z')"
echo ""
echo "${OUTPUT}"
exit 1
