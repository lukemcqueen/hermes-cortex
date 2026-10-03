#!/usr/bin/env bash
# Regenerate docs/evidence/gateway-new-command-evidence.md.
#
# The evidence is produced by RUNNING the deployed gateway against the real agent,
# never written by hand — so it cannot drift from what the host actually does.
#
#   bash ops/scripts/cortex_gateway/run-new-command-evidence.sh
#
# Exits non-zero when any acceptance criterion fails, so it is usable as a gate.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${REPO}/docs/evidence/gateway-new-command-evidence.md"
PY="${EVIDENCE_PY:-$(command -v python3)}"

# /usr/bin/python3 has no pytest, but this script needs no test deps — only the
# stdlib plus the deployed gateway modules.
echo "interpreter: ${PY}"

mkdir -p "$(dirname "${OUT}")"
"${PY}" "${REPO}/ops/scripts/cortex_gateway/new_command_evidence.py" > "${OUT}"
rc=$?                      # capture BEFORE anything else consumes it

echo "wrote ${OUT} ($(wc -l < "${OUT}") lines)"
if [ "${rc}" -ne 0 ]; then
  echo "EVIDENCE FAILED — see ${OUT}" >&2
  tail -20 "${OUT}" >&2
  exit "${rc}"
fi
echo "evidence PASSED"
