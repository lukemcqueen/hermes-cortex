#!/usr/bin/env bash
# Re-runnable proof for the nightly mycortex dream digest, 2026-10-12.
# Proves: (a) the dream file exists at its expected size and digest,
#         (b) the INDEX.md carries the appended 2026-10-12 row,
#         (c) both mycortex read commands used for the digest still return data.
# Exit 0 = all assertions held; non-zero = a named assertion failed.
set -u
fail=0

DREAM="$HOME/brain/esther/dreams/2026-10-12.md"
INDEX="$HOME/brain/esther/dreams/INDEX.md"
MYCORTEX="$HOME/.hermes-cortex/scripts/mycortex"
EXPECT_SIZE=4061
EXPECT_MD5=3a139c0106f752e546b8459dc7a38e0d

echo "== A. dream file: exists, exact size, exact digest =="
if [ -f "$DREAM" ]; then
  size=$(wc -c < "$DREAM")
  md5=$(md5sum "$DREAM" | cut -d' ' -f1)
  printf "   path=%s\n   size=%s (want %s)\n   md5=%s (want %s)\n" \
    "$DREAM" "$size" "$EXPECT_SIZE" "$md5" "$EXPECT_MD5"
  [ "$size" = "$EXPECT_SIZE" ] || { echo "   FAIL - size mismatch"; fail=1; }
  [ "$md5" = "$EXPECT_MD5" ]   || { echo "   FAIL - digest mismatch"; fail=1; }
else
  echo "   FAIL - $DREAM does not exist"; fail=1
fi

echo
echo "== B. INDEX.md carries the appended 2026-10-12 row (verbatim) =="
want='2026-10-12 | The Window That Would Not Narrow | Cycle 12154 answered one false attribution six times by shrinking the claim (owner is 507eea1e, range touches nothing of theirs), then the peer landed its own lesson — stranded skills 1 → 0; the window is not a verdict about you.'
last=$(tail -1 "$INDEX")
if [ "$last" = "$want" ]; then
  echo "   OK   - line 31 matches verbatim"
else
  echo "   FAIL - last line is:"; echo "     $last"; fail=1
fi
rows=$(grep -c '^2026-10-12 |' "$INDEX")
printf "   rows dated 2026-10-12: %s (want 1)\n" "$rows"
[ "$rows" = "1" ] || { echo "   FAIL - expected exactly one 2026-10-12 row"; fail=1; }

echo
echo "== C. the mycortex reads the digest cites still return data =="
list_out=$(python3 "$MYCORTEX" list -n 20 2>/dev/null)
list_n=$(printf '%s\n' "$list_out" | grep -c 'hermes-cortex\|esther')
printf "   mycortex list -n 20 -> %s pages\n" "$list_n"
[ "$list_n" -ge 20 ] || { echo "   FAIL - list returned fewer than 20 pages"; fail=1; }

drift=$(python3 "$MYCORTEX" search "stranded skill drift deployed" --limit 3 2>/dev/null | head -1)
printf "   mycortex search 'stranded skill drift deployed' -> %s\n" "$drift"
printf '%s' "$drift" | grep -q '0\.99' || { echo "   FAIL - search returned no ranked hit"; fail=1; }

echo
echo "== D. the git evidence the digest cites is real =="
cd "$HOME/hermes-cortex" || { echo "   FAIL - repo missing"; exit 1; }
for sha in d2ab1cb6 d91f3a61 d8373daa 1a57f7a0 507eea1e; do
  subj=$(git log --format='%s' -1 "$sha" 2>/dev/null)
  printf "   %s  %s\n" "$sha" "${subj:-<NOT FOUND>}"
  [ -n "$subj" ] || { echo "     FAIL - $sha not in history"; fail=1; }
done

echo
echo "== E. the digest's central count: stranded == 0 =="
stranded=$(grep 'Deployed-only files (stranded)' docs/evidence/skill-drift-parity.txt | grep -o '[0-9]\+')
printf "   stranded=%s (want 0)\n" "${stranded:-<none>}"
[ "${stranded:-x}" = "0" ] || { echo "   FAIL - stranded count is not 0"; fail=1; }

echo
if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS - all assertions held"
else
  echo "RESULT: one or more assertions did not hold"
fi
exit "$fail"
