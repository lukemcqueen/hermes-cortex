#!/usr/bin/env bash
# Verify cycle 12307's own claims in ONE run, as the close review asked:
#   - every checksum PUBLISHED in closeout-cycle-12307-proof.txt matches the file at HEAD
#   - the negative check is really negative (no verifier invokes a drifted skill)
#   - the dogfood transcript carries the two lines quoted from it
# Exits non-zero on any failed claim. The published values are PARSED from the proof file
# rather than repeated here, so this tests what was published, not a copy of it.
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2
PROOF=docs/evidence/closeout-cycle-12307-proof.txt
FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

say "cycle 12307 verifier — repo=$REPO  head=$(git rev-parse --short HEAD)"
say

# 1 — published checksums vs the committed bytes
say "1  every published checksum, recomputed from HEAD"
checked=0
while read -r want name; do
  case "$want" in *[!0-9a-f]*) continue;; esac        # skip header/notes lines
  [ "${#want}" -ge 8 ] || continue
  file="docs/evidence/$name"
  if ! git cat-file -e "HEAD:$file" 2>/dev/null; then bad "1 $file is not committed at HEAD"; continue; fi
  got=$(git show "HEAD:$file" | sha256sum | cut -c1-12)
  checked=$((checked + 1))
  if [ "$got" = "$want" ]; then say "   OK    $want  $name"
  else bad "1 $name: published $want, HEAD has $got"; fi
done < <(sed -n '1,12p' "$PROOF" | awk 'NF>=2 && $1 ~ /^[0-9a-f]+$/ {print $1, $2}')
[ "$checked" -ge 4 ] || bad "1 expected at least 4 published checksums, parsed $checked"
say "   ($checked checksums parsed from $PROOF)"

# 2 — the negative check: no verifier invokes a drifted skill
say "2  negative check: does any verifier reference a drifted skill?"
hits=$(grep -l -e survey-before-action -e change-checklist -e shell-scripting \
        -e shared-repo-push-gates -e hermes-gateway-operations \
        docs/evidence/pi-mcp-landing-verify.sh docs/evidence/session-cache-loop-evaluator-verify.sh \
        docs/evidence/launchd-restart-12223-reproduce.sh 2>/dev/null || true)
if [ -z "$hits" ]; then say "   OK    grep -l over the three verifiers: no output (no match)"
else bad "2 a verifier references a drifted skill: $hits"; fi

# 3 — the dogfood transcript's two quoted lines
say "3  the dogfood lines quoted in the material"
dog=docs/evidence/dogfood-strands-landing-2026-10-12.txt
grep -q 'Overall: WARNING' "$dog" && say "   OK    carries the Overall line" || bad "3 no Overall line in $dog"
grep -q 'DOGFOOD PASSED'  "$dog" && say "   OK    carries the tool's closing line" || bad "3 no DOGFOOD PASSED line"
say "   (the file labels itself DECISIVE LINES ONLY — a summary, not a transcript)"

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
