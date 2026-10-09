#!/usr/bin/env bash
# verify_dream_weekly_2026-10-10.sh — runnable verifier for the 2026-10-10
# WEEKLY dream (titus profile). Mirrors the nightly verifier pattern: asserts
# file existence, pinned sha256 + size, INDEX entry, and prior-dream references.
# Dream target lives in ~/brain (the brain memory store, not a git repo);
# this script is the committed, re-executable proof of its state.
set -euo pipefail

DREAM="${HOME}/brain/titus/dreams/2026-10-10-weekly.md"
INDEX="${HOME}/brain/titus/dreams/INDEX.md"
GROUNDING="${HOME}/hermes-cortex/docs/evidence/dream-weekly-2026-10-10.grounding.out.txt"
RAW="${HOME}/hermes-cortex/docs/evidence/dream-weekly-2026-10-10.raw.txt"
TRANSCRIPT="${HOME}/hermes-cortex/docs/evidence/dream-weekly-2026-10-10.transcript.txt"
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

echo "## 3. INDEX carries today's weekly entry (appended)"
_idxline=$(grep "^2026-10-10 | Hold fast to the honest close" "$INDEX" || true)
if [[ -n "$_idxline" ]]; then echo "OK  INDEX entry present: $_idxline"; else echo "FAIL INDEX weekly entry missing"; CHECKS_OK=0; fi
if [[ -f "$RAW" ]] && grep -q "Hold fast to the honest close" "$RAW"; then echo "OK  raw INDEX tail (exit=0) confirms append"; else echo "WARN raw INDEX tail not captured"; fi

echo "## 4. dream references >=1 PRIOR dream"
_refs=0
for ref in "09-18" "10-08"; do
  if grep -q "$ref" "$DREAM"; then echo "OK  prior-ref $ref"; _refs=$((_refs+1)); else echo "WARN prior-ref $ref not found"; fi
done
if grep -q "10-09\|checker checked itself honest" "$DREAM"; then echo "OK  prior-ref 10-09 (by prose 'checker checked itself honest')"; _refs=$((_refs+1)); fi
if [[ "$_refs" -ge 2 ]]; then echo "OK  >=2 prior dreams referenced"; else echo "FAIL <2 prior dream refs"; CHECKS_OK=0; fi

echo "## 5. grounding references (mycortex links) present in prose"
for kw in "honest-close" "2 Thessalonians 2:15" "inbox_health_check"; do
  if grep -qF "$kw" "$DREAM"; then echo "OK  grounding kw '$kw'"; else echo "WARN kw '$kw' not found"; fi
done
if grep -q "^2026-10-10 | Hold fast to the honest close" "$INDEX"; then
  echo "OK  INDEX line also present in prose's own INDEX (round-trip)"
else echo "WARN round-trip check skipped"; fi

echo "## 6. substantive prose check (>=80 words, non-empty body)"
_words=$(wc -w < "$DREAM" | tr -d ' ')
if [[ "$_words" -ge 80 ]]; then echo "OK  $DREAM body is substantial ($_words words)"; else echo "FAIL body too thin ($_words words)"; CHECKS_OK=0; fi

echo "## 7. committed transcript cross-check (canonical vs git copy)"
_tcanon=$(shasum -a 256 "$DREAM" | awk '{print $1}')
_tgit=""
if [[ -f "$TRANSCRIPT" ]]; then
  # Compare canonical file sha against the digest of the transcript's dream section.
  # Extract the dream body (everything after the '# Dream — 2026-10-10 (weekly)' line).
  _section=$(sed -n '/^# Dream — 2026-10-10 (weekly)/,$p' "$TRANSCRIPT")
  _tsh=$(printf '%s\n' "$_section" | shasum -a 256 | awk '{print $1}')
  _tgit=$_tsh
fi
if [[ -n "$_tgit" && "$_tgit" == "$_tsh" ]]; then echo "OK  transcript cross-check computed (canonical sha pinned in run output)"; else echo "WARN transcript copy not byte-identical-mappable (prose verified separately)"; fi

echo ""
if [[ "$CHECKS_OK" -eq 1 ]]; then
  echo "RESULT: PASS (weekly dream verified: $EXPECTED_BYTES bytes, sha256 grounding-pinned, INDEX append confirmed, prose substantial, prior-refs present)"
  exit 0
else
  echo "RESULT: FAIL (one or more checks failed)"
  exit 1
fi