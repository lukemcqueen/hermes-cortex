#!/usr/bin/env bash
# Regenerate docs/evidence/soul-refine-12624-2026-10-14.txt — the soul-refinement
# cycle 12624 evidence capture. Read-only except for writing the target file.
set -uo pipefail
REPO="${1:-/home/esther/hermes-cortex}"
OUT="$REPO/docs/evidence/soul-refine-12624-2026-10-14.txt"
PY=~/.hermes-cortex/venv/bin/python3
: > "$OUT"
{
  echo "SOUL-REFINEMENT CYCLE 12624 — EVIDENCE CAPTURE (regenerated $(date -u +%FT%TZ))"
  echo "===[B1] review-provenance gate on the live repo"
  ( cd "$REPO" && python3 ops/scripts/quality/review-provenance-check.py --repo . 2>&1; echo "rc=$?" )
  echo "===[B2] the gate's hermetic test file"
  ( cd "$REPO" && "$PY" -m pytest tests/test_review_provenance_check.py -q 2>&1 | tail -3; echo "rc=${PIPESTATUS[0]}" )
  echo "===[B3] tree and origin"
  ( cd "$REPO" && git status --porcelain; echo "rc=$?"; git rev-parse HEAD origin/main; echo "rc=$?" )
} >> "$OUT"
echo "wrote $OUT ($(wc -c < "$OUT") bytes)"
