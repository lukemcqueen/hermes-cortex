#!/usr/bin/env bash
# Regenerate docs/evidence/pii-gate-redaction-evidence.txt (ADV-10571-1).
#
#   bash ops/scripts/manage/run-pii-gate-evidence.sh
#
# Exit 0 = the redaction claim holds: the guard discriminates (it trips on the
# pre-fix revision) and the redacted test file carries no identifier component
# and passes. Exit 1 = the claim is false; do not ship.
#
# Not a deployed script — a repo-local evidence generator, like
# run-task-queue-evidence.sh. tests/test_pii_gate_evidence.py re-runs it in
# --check mode so the committed artifact cannot be hand-written.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec python3 "${REPO}/ops/scripts/manage/pii-gate-evidence.py" "$@"
