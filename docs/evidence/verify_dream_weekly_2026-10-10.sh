#!/usr/bin/env bash
# verify_dream_weekly_2026-10-10.sh — runnable verifier for the 2026-10-10
# WEEKLY dream (titus profile). Mirrors the nightly verifier pattern: asserts
# file existence, pinned sha256 + size, INDEX entry, and prior-dream references.
# Dream target lives in ~/brain BY DESIGN (brain memory, not the git repo);
# this script is the committed, re-executable proof of its state.
set -euo pipefail

DREAM="${HOME}/brain/titus/dreams/2026-10-10-weekly.md"
INDEX="${HOME}/brain/titus/dreams/INDEX.md"
GROUNDING="${HOME}/hermes-cortex/docs/evidence/dream-weekly-2026-10-10.grounding.out.txt"
EXPECTED_BYTES=1627
CHECKS_OK=1

echo "## 0. expected-hash present in committed grounding output"
EXPECTED_SHA=""
if [[ -f "$GROUNDING" ]]; then
  EXPECTED_SHA=$(grep -E '^[0-9a-f]{64}  '"$DREAM"'$' "$GROUNDING" | awk '{print $1}')
fi
if [[ -n "$EXPECTED_SHA" ]]; then echo "OK  grounded sha256 available ($GROUNDING)"; else echo "FAIL grounding hash missing"; CHECKS_OK=0; fi

echo "## 1. weekly dream file present, non-empty"
if [[ -s "$DREAM" ]]; then echo "OK  $DREAM present and non-empty"; else echo "FAIL missing/empty"; CHECKS_OK=0; fi

echo "## 2. pinned sha256 + size (byte for byte)"
_sz=$(wc -c < "$DREAM" | tr -d ' ')
_sha=$(shasum -a 256 "$DREAM" | awk '{print $1}')
if [[ "$_sz" -eq "$EXPECTED_BYTES" ]]; then echo "OK  size $_sz matches pinned $EXPECTED_BYTES"; else echo "FAIL size $_sz != $EXPECTED_BYTES"; CHECKS_OK=0; fi
if [[ -n "$EXPECTED_SHA" && "$_sha" == "$EXPECTED_SHA" ]]; then echo "OK  sha256 matches grounding-pinned"; else echo "FAIL sha256 $_sha"; CHECKS_OK=0; fi

echo "## 3. INDEX carries today's weekly entry"
if grep -q "^2026-10-10 | Hold fast to the honest close" "$INDEX"; then
  echo "OK  INDEX entry present: $(grep '^2026-10-10 | Hold fast' "$INDEX")"
else echo "FAIL INDEX weekly entry missing"; CHECKS_OK=0; fi

echo "## 4. dream references >=1 PRIOR dream"
_refs=0
for ref in "09-18" "10-08" "10-09"; do
  if grep -q "$ref" "$DREAM"; then echo "OK  prior-ref $ref"; _refs=$((_refs+1)); else echo "WARN prior-ref $ref not found"; fi
done
if [[ "$_refs" -ge 1 ]]; then echo "OK  >=1 prior dream referenced"; else echo "FAIL no prior dream refs"; CHECKS_OK=0; fi

echo "## 5. grounding references (mycortex links) present in prose"
for kw in "honest-close" "2 Thessalonians 2:15" "inbox_health_check"; do
  if grep -qF "$kw" "$DREAM"; then echo "OK  grounding kw '$kw'"; else echo "WARN kw '$kw' not found"; fi
done

echo ""
if [[ "$CHECKS_OK" -eq 1 ]]; then
  echo "RESULT: PASS (weekly dream verified: $EXPECTED_BYTES bytes, sha256 grounding-pinned)"
  exit 0
else
  echo "RESULT: FAIL (one or more checks failed)"
  exit 1
fi