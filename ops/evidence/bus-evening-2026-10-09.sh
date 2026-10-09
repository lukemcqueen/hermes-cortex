#!/usr/bin/env bash
# Generate the bus-evening evidence artifact from the COMMITTED, read-only
# bus inspector (ops/scripts/orch-bus/bus-inbox-inspect.py — GET
# /api/pgmq/queues and /api/pgmq/peek only; never consumes a message).
#
# Re-runnable at HEAD: it runs the inspector in both modes and writes
# docs/evidence/bus-evening-2026-10-09.txt. Host-identifying strings (the
# home dir, every bus endpoint URL, and long numeric ids such as chat/phone
# numbers) are scrubbed at the SOURCE so the committed artifact carries no real
# paths, domains, endpoints or identifiers.
#
# It also records the agent-message-handler classification output for the
# subjects seen in flight (why HEALTH_* / protocol probes need no pickup
# notify), so the benign-ness of those envelopes is committed, re-executable
# proof rather than prose.
#
# Usage: bash ops/evidence/bus-evening-2026-10-09.sh
# Read-only: it never sends, archives, or consumes a bus message.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSPECTOR_REL="ops/scripts/orch-bus/bus-inbox-inspect.py"
INSPECTOR="${REPO}/${INSPECTOR_REL}"
HANDLER_REL="ops/scripts/agent/agent-message-handler.py"
HANDLER="${REPO}/${HANDLER_REL}"
[[ -f "${INSPECTOR}" ]] || {
  echo "FATAL: ${INSPECTOR_REL} not found under ${REPO}; cannot generate evidence" >&2
  exit 3
}
ARTIFACT="${REPO}/docs/evidence/bus-evening-2026-10-09.txt"

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

# Classification proof: which in-flight subjects are protocol/health noise that
# the handler intentionally does not pickup-notify. Fail loudly if it cannot run.
OUT_RULE="$(python3 - "${HANDLER}" <<'PY' 2>&1
import importlib.util, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts"))
handler = sys.argv[1]
spec = importlib.util.spec_from_file_location("amh", handler)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
for s in ("HEALTH_PERSISTENT_ISSUES", "DOCTOR_TEST", "UPDATE_REQUEST"):
    print(f"_is_silent_subject({s!r}) = {m._is_silent_subject(s)}")
PY
)"
RC_RULE=$?

# Fail closed: never emit a "successful" artifact from a failed probe.
if [[ ${RC_ISSUES} -ne 0 || ${RC_FULL} -ne 0 || ${RC_RULE} -ne 0 ]]; then
  echo "FATAL: inspector/rule probe failed (issues=${RC_ISSUES} full=${RC_FULL} rule=${RC_RULE})" >&2
  exit 1
fi

{
  echo "# Bus evening inspection — GENERATED artifact (not hand-written)"
  echo "# generated_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# inspector_revision: ${REV}"
  echo "# generator: ops/evidence/bus-evening-2026-10-09.sh"
  echo "# inspector: ${INSPECTOR_REL} (committed, read-only, never consumes)"
  echo "# command: python3 ${INSPECTOR_REL} esther --issues"
  echo "# command: python3 ${INSPECTOR_REL} esther"
  echo "# command: _is_silent_subject() probe over ${HANDLER_REL}"
  echo "# scrubbed at source: <home>, <bus-endpoint>, <redacted-id>."
  echo ""
  echo "## --issues (empty stdout + exit 0 == no-action / silent condition)"
  echo "issues_exit=${RC_ISSUES}"
  printf '%s\n' "${OUT_ISSUES}" | scrub
  echo ""
  echo "## handler classification of in-flight subjects (rule_probe_exit=${RC_RULE})"
  printf '%s\n' "${OUT_RULE}" | scrub
  echo ""
  echo "## full JSON transcript (inspector output is scrubbed/truncated at source)"
  echo "transcript_exit=${RC_FULL}"
  printf '%s\n' "${OUT_FULL}" | scrub
  echo ""
} > "${ARTIFACT}"

echo "wrote ${ARTIFACT} ($(wc -c < "${ARTIFACT}") bytes) issues_exit=${RC_ISSUES} rule_exit=${RC_RULE}"
