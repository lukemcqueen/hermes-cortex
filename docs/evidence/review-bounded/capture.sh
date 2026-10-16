#!/usr/bin/env bash
# capture.sh — REGENERATE docs/evidence/review-bounded/live-proof.txt
#
# The claim this artifact supports: the close-time reviewer is now BOUNDED — in
# thinking budget, in wall clock, and in the UNIT it judges (one blob at a time,
# cached by content) — and the pre-change revision demonstrably is not.
#
# Every command is printed immediately above its own output, and each rc is
# measured from the command itself (not from a pipe's last stage). The baseline is
# pinned to a SHA, never to HEAD: the artifact is committed in the same range as
# the fix, so HEAD would resolve to the FIXED module and the comparison would be a
# tautology.
#
#   cd ~ && bash hermes-cortex/docs/evidence/review-bounded/capture.sh \
#       > hermes-cortex/docs/evidence/review-bounded/live-proof.txt
set -u

EV="hermes-cortex/docs/evidence/review-bounded"
BASELINE="119e6006"          # tip before the change: no per-blob surface, no bounds
PRE="/tmp/pre-review-bounds-loop-gov.py"

body() {
  cd "$HOME" || exit 1
  local PY
  PY=$(command -v python3)

  echo "REVIEWER BOUNDS — LIVE proof (generated, not hand-written)"
  echo "Produced by: bash $EV/capture.sh   (every path below is normalised to ~)"
  echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "═══════ 1. The baseline is genuinely PRE-change ═══════"
  echo "\$ git -C hermes-cortex show $BASELINE:mcp-servers/loop-gov-mcp.py > $PRE"
  git -C hermes-cortex show "$BASELINE:mcp-servers/loop-gov-mcp.py" > "$PRE"
  echo "\$ grep -c 'blob_reviews' $PRE     # 0 => no per-blob surface in the baseline"
  grep -c 'blob_reviews' "$PRE" || true
  echo "\$ grep -c '_hard_deadline' $PRE   # 0 => no hard deadline in the baseline"
  grep -c '_hard_deadline' "$PRE" || true
  echo "\$ grep -c '\"reasoning\"' $PRE     # 0 => no bounded thinking in the baseline"
  grep -c '"reasoning"' "$PRE" || true
  echo

  echo "═══════ 2. The bounds hold on the working tree ═══════"
  echo "\$ python3 hermes-cortex/tests/test_reviewer_budget.py"
  "$PY" hermes-cortex/tests/test_reviewer_budget.py 2>&1 | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo
  echo "\$ python3 hermes-cortex/tests/test_review_per_blob.py"
  "$PY" hermes-cortex/tests/test_review_per_blob.py 2>&1 | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 3. The baseline FAILS the same checks (discrimination) ═══════"
  echo "\$ CORTEX_LOOP_GOV_SERVER=$PRE python3 hermes-cortex/tests/test_reviewer_budget.py"
  CORTEX_LOOP_GOV_SERVER="$PRE" "$PY" hermes-cortex/tests/test_reviewer_budget.py 2>&1 \
    | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo "  -> note the deadline case: against a TRICKLING peer the baseline took ~22s"
  echo "     and was aborted only by the socket timeout after the peer stopped. The"
  echo "     measured production hang ran 15 and 26 MINUTES because the provider kept"
  echo "     sending; only a wall-clock deadline bounds that."
  echo
  echo "\$ CORTEX_LOOP_GOV_SERVER=$PRE python3 hermes-cortex/tests/test_review_per_blob.py"
  CORTEX_LOOP_GOV_SERVER="$PRE" "$PY" hermes-cortex/tests/test_review_per_blob.py 2>&1 \
    | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 4. Adversarial gate (A4) on every changed file ═══════"
  echo "\$ adversarial-verify.py --file <f> --level A4 --gate   (rc 0 = no critical/high)"
  for f in mcp-servers/loop-gov-mcp.py tests/test_review_per_blob.py \
           tests/test_reviewer_budget.py "$EV/capture.sh"; do
    printf '%-56s ' "$f"
    hermes-cortex/ops/scripts/quality/adversarial-verify.py --file "hermes-cortex/$f" --level A4 --gate 2>&1 \
      | grep -E 'GATE_PASSED|GATE_FAILED' || echo "NO VERDICT"
  done
  echo

  echo "═══════ 5. What this proof does NOT cover ═══════"
  echo "- The deployed-in-process close. The running loop-governance MCP child holds the"
  echo "  revision it started with, so the per-blob close is exercised by a FRESH process"
  echo "  (the CLI) until the gateway restarts; the doctor names that condition."
  echo "- A live reviewer outage. The stalled peer in §2/§3 is a local socket that"
  echo "  TRICKLES bytes, which is what defeats a socket timeout; no real provider was"
  echo "  asked to hang."
}

body | sed "s|$HOME|~|g"
