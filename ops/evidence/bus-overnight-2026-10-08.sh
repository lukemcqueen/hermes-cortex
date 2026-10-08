#!/usr/bin/env bash
# Generate the bus-overnight evidence artifact from the COMMITTED, read-only
# bus inspector (ops/scripts/orch-bus/bus-inbox-inspect.py — GET
# /api/pgmq/queues and /api/pgmq/peek only; never consumes a message).
#
# Re-runnable at HEAD: it runs the inspector in both modes and writes
# docs/evidence/bus-overnight-2026-10-08.txt. Host-identifying strings (the
# home dir, every bus endpoint URL, and long numeric ids such as chat/phone
# numbers) are scrubbed at the SOURCE so the committed artifact carries no real
# paths, domains, endpoints or identifiers.
#
# Usage: bash ops/evidence/bus-overnight-2026-10-08.sh
# Read-only: it never sends, archives, or consumes a bus message.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSPECTOR="${REPO}/ops/scripts/orch-bus/bus-inbox-inspect.py"
[[ -f "${INSPECTOR}" ]] || INSPECTOR="${HOME}/.hermes-cortex/scripts/bus-inbox-inspect.py"
ARTIFACT="${REPO}/docs/evidence/bus-overnight-2026-10-08.txt"

scrub() {
  sed -E \
    -e "s#${HOME}#<home>#g" \
    -e 's#https?://[^[:space:]"'"'"'<>]+#<bus-endpoint>#g' \
    -e 's#[0-9]{8,}#<redacted-id>#g'
}

REV="$(git -C "${REPO}" rev-parse --short HEAD)"

OUT_ISSUES="$(python3 "${INSPECTOR}" esther --issues 2>&1)"
RC_ISSUES=$?
OUT_FULL="$(python3 "${INSPECTOR}" esther 2>&1)"
RC_FULL=$?

{
  echo "# Bus overnight inspection — GENERATED artifact (not hand-written)"
  echo "# generated_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# inspector_revision: ${REV}"
  echo "# generator: ops/evidence/bus-overnight-2026-10-08.sh"
  echo "# inspector: ops/scripts/orch-bus/bus-inbox-inspect.py (committed, read-only, never consumes)"
  echo "# command: python3 <home>/.hermes-cortex/scripts/bus-inbox-inspect.py esther --issues"
  echo "# command: python3 <home>/.hermes-cortex/scripts/bus-inbox-inspect.py esther"
  echo "# scrubbed at source: <home>, <bus-endpoint>, <redacted-id>."
  echo ""
  echo "## --issues (empty stdout + exit 0 == no-action / silent condition)"
  echo "issues_exit=${RC_ISSUES}"
  printf '%s\n' "${OUT_ISSUES}" | scrub
  echo ""
  echo "## full JSON transcript"
  echo "transcript_exit=${RC_FULL}"
  printf '%s\n' "${OUT_FULL}" | scrub
  echo ""
} > "${ARTIFACT}"

echo "wrote ${ARTIFACT} ($(wc -c < "${ARTIFACT}") bytes) issues_exit=${RC_ISSUES}"
