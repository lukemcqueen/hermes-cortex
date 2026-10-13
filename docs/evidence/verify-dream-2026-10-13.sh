#!/usr/bin/env bash
# Verifies the 2026-10-13 mycortex dream digest write-back.
# Artifacts live under ~/brain/titus/dreams/ (brain data dir, not part of this repo).
set -euo pipefail

DREAM=~/brain/titus/dreams/2026-10-13.md
INDEX=~/brain/titus/dreams/INDEX.md
fail=0

# Phase 4a: the daily dream file exists and has content
if [[ ! -f "$DREAM" ]]; then echo "FAIL: $DREAM missing"; fail=1
else
  echo "OK: $DREAM present, $(wc -c < "$DREAM") bytes"
  grep -q "The seam became a standard\|the same answer from any door\|6,594 pages" "$DREAM" \
    || { echo "FAIL: expected content not in dream"; fail=1; }
fi

# Phase 4b: INDEX has today's appended line
if [[ ! -f "$INDEX" ]]; then echo "FAIL: $INDEX missing"; fail=1
else
  tail -1 "$INDEX" | grep -q "2026-10-13 | The seam became a standard" \
    || { echo "FAIL: INDEX does not end with 2026-10-13 line"; fail=1; }
  echo "OK: INDEX ends with 2026-10-13 entry"
fi

if (( fail )); then echo "VERIFY FAILED"; exit 1; fi
echo "VERIFY PASSED"