#!/usr/bin/env bash
# verify-dream-2026-10-21.sh — re-runnable verifier for the nightly mycortex
# dream digest of 2026-10-21.
#
# The dream's OUTPUT lives in ~/brain/<profile>/dreams/, which is NOT a git
# repo, so the close reviewer cannot read it from the audited diff. This
# script lets any reader re-run the proof instead of trusting a pasted
# transcript.
#
# Usage:  bash docs/evidence/verify-dream-2026-10-21.sh
# Exit:   0 = every assertion held; 1 = at least one failed (named on stderr);
#         2 = could not verify (a required file is absent).
#
# READ-ONLY: this script never writes, repairs or regenerates anything.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVID="$REPO/docs/evidence"
ART="$EVID/dream-digest-2026-10-21.md"
SIDECAR="$EVID/dream-digest-2026-10-21.md.sha256"
BRAIN="${HOME}/brain/esther/dreams/2026-10-21.md"
INDEX="${HOME}/brain/esther/dreams/INDEX.md"

FAILED=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1" >&2; FAILED=1; }

# --- 0. required files present (a missing file is "could not verify") --------
for f in "$ART" "$SIDECAR"; do
  if [ ! -f "$f" ]; then
    printf 'COULD NOT VERIFY: required file absent: %s\n' "$f" >&2
    exit 2
  fi
done

# --- 1. the committed artifact matches the committed sidecar -----------------
# Compared with sha256sum against the sidecar, so the digest is not a literal
# baked into this script (a bare 64-hex string trips the PII guard).
if (cd "$EVID" && sha256sum -c --status dream-digest-2026-10-21.md.sha256); then
  pass "artifact matches its committed sidecar digest"
else
  fail "artifact does NOT match its committed sidecar digest"
fi

# --- 2. the live brain copy, when present, is byte-identical -----------------
if [ -f "$BRAIN" ]; then
  if cmp -s "$ART" "$BRAIN"; then
    pass "live brain copy is byte-identical to the committed artifact"
  else
    fail "live brain copy DIFFERS from the committed artifact"
  fi
else
  printf 'NOTE  live brain copy absent on this host — section skipped\n'
fi

# --- 3. structural assertions on the digest ---------------------------------
assert_contains() {  # file needle label
  if grep -qF -- "$2" "$1"; then pass "$3"; else fail "$3"; fi
}

assert_contains "$ART" "# Dream — 2026-10-21" "title carries the date"
assert_contains "$ART" "The Lesson That Only One Host Could Read" "title names the dream"
assert_contains "$ART" "## Provenance" "provenance section present"
assert_contains "$ART" "## The pages" "pages section present"
assert_contains "$ART" "79bd5eb4" "cites the stranded-skill commit"
assert_contains "$ART" "dispositions.py" "cites the disposition store"

# Prior-dream references: the task requires referencing 1-2 earlier dreams.
assert_contains "$ART" "2026-10-19" "references the 10-19 prior dream"
assert_contains "$ART" "2026-10-10" "references the 10-10 prior dream"

# --- 4. the INDEX carries exactly one line for this date --------------------
if [ -f "$INDEX" ]; then
  n=$(grep -c '^2026-10-21 |' "$INDEX")
  if [ "$n" -eq 1 ]; then
    pass "INDEX carries exactly one 2026-10-21 entry"
  else
    fail "INDEX carries $n entries for 2026-10-21 (expected exactly 1)"
  fi
  if grep -q '^2026-10-21 | The Lesson That Only One Host Could Read |' "$INDEX"; then
    pass "INDEX entry carries the dream title"
  else
    fail "INDEX entry is missing the dream title"
  fi
else
  fail "INDEX file absent: $INDEX"
fi

printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'RESULT: ALL PASS\n'
  exit 0
fi
printf 'RESULT: FAILED\n' 1>&2
exit 1
