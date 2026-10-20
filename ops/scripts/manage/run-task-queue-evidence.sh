#!/usr/bin/env bash
# Regenerate docs/evidence/task-queue-remediation.md.
#
# The evidence is produced by RUNNING the checks against the live store, never
# written by hand — so it cannot drift from what the system actually does.
#
#   bash ops/scripts/manage/run-task-queue-evidence.sh
#
# Exits non-zero when any check fails, so it is usable as a gate.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${REPO}/docs/evidence/task-queue-remediation.md"

# Resolve the interpreter by CAPABILITY, not by PATH existence: `command -v python3`
# says a file exists and nothing at all about the module it must import. On the cron
# PATH it resolved to the agent runtime interpreter, which has no pytest — measured
# 2026-10-20, where the run printed "No module named pytest" in place of the suite
# output and still reported "evidence PASSED".
PY="${EVIDENCE_PY:-$(bash "${REPO}/ops/scripts/lib/python-with-module.sh" --print pytest)}"
if [ -z "${PY}" ] || [ ! -x "${PY}" ]; then
  echo "COULD NOT VERIFY — no interpreter on this host can import pytest" >&2
  echo "  refusing to emit a report whose load-bearing section would be an error" >&2
  exit 3
fi

echo "interpreter: ${PY}"
mkdir -p "$(dirname "${OUT}")"

"${PY}" "${REPO}/ops/scripts/manage/task-queue-evidence.py" > "${OUT}"
rc=$?                      # capture BEFORE anything else reads $?

echo "wrote ${OUT} ($(wc -l < "${OUT}") lines)"
if [ "${rc}" -ne 0 ]; then
  echo "EVIDENCE FAILED — see ${OUT}" >&2
  tail -20 "${OUT}" >&2
  exit "${rc}"
fi
echo "evidence PASSED"
