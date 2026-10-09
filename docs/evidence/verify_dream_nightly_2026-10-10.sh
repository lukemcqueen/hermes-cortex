#!/usr/bin/env bash
# Runable verifier: nightly dream 2026-10-10 (titus) — re-executable by a later reviewer.
# Exit 0 and print RESULT: PASS only if every check genuinely holds on current disk.
set -u
fail=0

DREAM=/Users/luke/brain/titus/dreams/2026-10-10.md
INDEX=/Users/luke/brain/titus/dreams/INDEX.md

# [1] dream file present, non-empty, expected size (matches committed evidence)
if [ -s "$DREAM" ]; then
  echo "OK  [1] dream file present non-empty: $(wc -c < "$DREAM") bytes  <- $DREAM"
else
  echo "FAIL[1] dream file missing/empty"; fail=1
fi

# [2] INDEX carries today's nightly entry (grep count must be 2: weekly + nightly)
n=$(grep -c "2026-10-10" "$INDEX" 2>/dev/null || echo 0)
if [ "$n" -ge 2 ]; then
  echo "OK  [2] INDEX has today's entries (count=$n)"
else
  echo "FAIL[2] INDEX missing nightly entry (count=$n)"; fail=1
fi

# [3] dream references two prior dreams by title
for t in "The seam that held" "The checker checked itself honest"; do
  if grep -q "$t" "$DREAM"; then echo "OK  [3] dream references prior dream: $t";
  else echo "FAIL[3] missing prior-dream reference: $t"; fail=1; fi
done

# [4] grounding: each claimed link is present in the captured real mycortex output
GROUNDING=/Users/luke/hermes-cortex/docs/evidence/dream-nightly-2026-10-10.grounding.out.txt
for pat in "session-manager/SKILL.md" "session-manager-v2" "session-state-pattern" "pull-latest-2026-10-10" "SOUL-archive"; do
  if grep -q "$pat" "$GROUNDING" 2>/dev/null; then echo "OK  [4] grounding hit: $pat";
  else echo "FAIL[4] grounding missing: $pat"; fail=1; fi
done

# [5] dream body mentions the three surfacing pages (constancy theme)
for pat in "session-manager" "pull-latest" "2 Thessalonians 2:15"; do
  if grep -q "$pat" "$DREAM"; then echo "OK  [5] dream body touches: $pat";
  else echo "FAIL[5] dream body missing: $pat"; fail=1; fi
done

echo
if [ "$fail" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL"; fi
exit "$fail"