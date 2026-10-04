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
PY="${EVIDENCE_PY:-$(command -v python3)}"

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
