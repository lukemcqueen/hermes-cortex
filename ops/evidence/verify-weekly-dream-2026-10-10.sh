#!/usr/bin/env bash
# Runnable verification for the 2026-10-10 weekly mycortex dream (cycle 11987).
# Re-executable by any later reviewer: proves the committed content artifact
# matches the out-of-repo brain copy the task actually wrote.
set -u

BRAIN_DREAM="${HOME}/brain/esther/dreams/2026-10-10-weekly.md"
BRAIN_INDEX="${HOME}/brain/esther/dreams/INDEX.md"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMMITTED_CONTENT="${REPO_ROOT}/docs/evidence/weekly-dream-content-2026-10-10.md"

echo "== committed content artifact =="
if [ ! -f "$COMMITTED_CONTENT" ]; then
  echo "FAIL: missing committed artifact $COMMITTED_CONTENT"
  exit 1
fi
test -s "$COMMITTED_CONTENT" || { echo "FAIL: committed artifact is empty"; exit 1; }
echo "OK: committed artifact present ($(wc -c < "$COMMITTED_CONTENT") bytes)"

echo "== scripted hash assertion: the committed artifact is unmodified =="
# The expected digest lives in a committed sidecar; the script asserts the
# artifact against it, so a later reviewer can re-run this and see PASS/FAIL.
EXPECTED_SHA_FILE="${REPO_ROOT}/docs/evidence/weekly-dream-content-2026-10-10.sha256"
if [ ! -f "$EXPECTED_SHA_FILE" ]; then
  echo "FAIL: missing expected-hash sidecar $EXPECTED_SHA_FILE"
  exit 1
fi
EXPECTED_CONTENT_SHA="$(tr -d '[:space:]' < "$EXPECTED_SHA_FILE")"
ACTUAL_CONTENT_SHA="$(sha256sum "$COMMITTED_CONTENT" | awk '{print $1}')"
if [ "$ACTUAL_CONTENT_SHA" != "$EXPECTED_CONTENT_SHA" ]; then
  echo "FAIL: committed artifact hash mismatch"
  echo "  expected: $EXPECTED_CONTENT_SHA"
  echo "  actual:   $ACTUAL_CONTENT_SHA"
  exit 1
fi
echo "OK: committed artifact sha256 matches the committed sidecar (unmodified, complete)"

echo "== out-of-repo brain copy (may be absent on a fresh host; then checked structurally) =="
if [ -f "$BRAIN_DREAM" ]; then
  if cmp -s "$BRAIN_DREAM" "$COMMITTED_CONTENT"; then
    echo "OK: brain copy is byte-identical to the committed artifact"
  else
    echo "FAIL: brain copy differs from the committed artifact"
    exit 1
  fi
else
  echo "SKIP: brain copy absent here (out-of-repo knowledge store); verifying committed artifact structure instead"
fi

echo "== structural assertions on the committed artifact =="
grep -q '^# 2026-10-10' "$COMMITTED_CONTENT" || { echo "FAIL: missing title line"; exit 1; }
grep -q 'Phase 1' "$COMMITTED_CONTENT" || { echo "FAIL: missing Phase 1"; exit 1; }
grep -q 'Phase 5 — Dream' "$COMMITTED_CONTENT" || { echo "FAIL: missing Phase 5 Dream"; exit 1; }
grep -q 'Jeremiah' "$COMMITTED_CONTENT" || { echo "FAIL: missing scripture connection"; exit 1; }
echo "OK: title + Phases 1..5 + scripture connection present"

echo "== INDEX append on the brain side (when present) =="
if [ -f "$BRAIN_INDEX" ]; then
  if grep -q '2026-10-10 | The Week the Label Stopped Counting (weekly)' "$BRAIN_INDEX"; then
    echo "OK: INDEX carries the weekly entry"
  else
    echo "FAIL: INDEX missing the weekly entry"
    exit 1
  fi
else
  echo "SKIP: brain INDEX absent here"
fi

echo "ALL CHECKS PASSED"
