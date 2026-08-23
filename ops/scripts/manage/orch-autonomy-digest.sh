#!/usr/bin/env bash
# orch-autonomy-digest — O4-S2 daily "what ran unattended" digest (no_agent).
# Runs the shadow-mode autonomy classifier digest for the last 24h and appends
# a tamper-evident ledger line. stdout is the delivery (compact daily digest).
# Expansion of the autonomy allowlist stays LOCKED until >=99% precision
# (O4-S1 evidence: 0.10% — far below bar; party design keeps pilot shadow-only).
set -uo pipefail

# Resolve the classifier: deployed location first, then repo fallback.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSIFIER=""
for cand in \
  "$SCRIPT_DIR/autonomy-classifier.py" \
  "$HOME/hermes-cortex/ops/scripts/manage/autonomy-classifier.py"; do
  if [ -f "$cand" ]; then CLASSIFIER="$cand"; break; fi
done

if [ -z "$CLASSIFIER" ]; then
  echo "[orch-autonomy-digest] $(date -u '+%Y-%m-%dT%H:%M:%SZ') ERROR: autonomy-classifier.py not found"
  exit 1
fi

# Kill switch — fail closed, silent no-op (AUTONOMY_CLASSIFIER_KILL=1).
if [ "${AUTONOMY_CLASSIFIER_KILL:-0}" = "1" ]; then
  exit 0
fi

python3 "$CLASSIFIER" --digest --hours 24 --ledger 2>&1
exit $?
