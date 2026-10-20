#!/usr/bin/env bash
# Re-runnable capture for the refused-close advisory's exit advice.
#
# Runs the advisory against a FIXTURE lock (never a real one) and prints, for the
# REPO copy and the DEPLOYED copy side by side:
#   - the rendered message,
#   - the advisory's own rc,
#   - counts measured over the CAPTURED MESSAGE ONLY, not over this transcript
#     (a count over the transcript would count the words in this script's own prose).
#
# Usage:  bash docs/evidence/refused-close-exit-advice-capture.sh
# Env:    DEPLOY_ROOT overrides ~/.hermes-cortex (tests/probes).
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO/ops/scripts/governance-refused-close-advisory.sh"
DEP="${DEPLOY_ROOT:-$HOME/.hermes-cortex}/scripts/governance-refused-close-advisory.sh"
SLUG="hermes-cortex"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/refused-adv.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/state"
cat > "$WORK/state/.governance-fixture.json" <<'JSON'
{"repo_slug":"hermes-cortex","task_id":"fix-refused-close-exit-advice","session_id":"fixture",
 "close_refused":{"at":"2026-10-20T16:00:00Z","cycle_id":10445,"verdict":"FINDINGS","blocking":4,
                  "finding_ids":["ADV-10445-1","ADV-10445-2"]}}
JSON

echo "refused-close advisory — exit advice, rendered"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "fixture lock: repo_slug=$SLUG task_id=fix-refused-close-exit-advice close_refused{cycle_id=10445,verdict=FINDINGS,blocking=4}"
echo "invocation:  GOVERNANCE_STATE_DIR=<fixture> bash <copy> $SLUG"
echo

for label in REPO DEPLOYED; do
  if [[ "$label" == "REPO" ]]; then copy="$SRC"; else copy="$DEP"; fi
  echo "=== $label copy ==="
  echo "path:   $copy"
  if [[ ! -f "$copy" ]]; then
    echo "MISSING — could not verify this copy"
    echo
    continue
  fi
  echo "sha256: $(sha256sum "$copy" | cut -d' ' -f1)"
  out="$WORK/out-$label.txt"
  GOVERNANCE_STATE_DIR="$WORK/state" bash "$copy" "$SLUG" > "$out" 2>&1
  rc=$?
  echo "--- message ---"
  cat "$out"
  echo "--- end message ---"
  echo "rc=$rc   (advisory contract: ALWAYS 0)"
  # Counts are over the CAPTURED MESSAGE ONLY.
  echo "in the message: names another agent as the exit = $(grep -c -i 'orchestrator' "$out")"
  echo "in the message: names advance_task_state        = $(grep -c 'advance_task_state' "$out")"
  echo "in the message: names the terminal state        = $(grep -c 'cancelled' "$out")"
  echo
done

echo "NOTES"
echo "  - The two sha256 differ BY DESIGN: the deployed copy carries a '# SOURCE:' header."
echo "  - Nothing here reads or writes a real governance lock: GOVERNANCE_STATE_DIR is a temp dir."
