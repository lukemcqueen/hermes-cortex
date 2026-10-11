#!/usr/bin/env bash
# Re-runnable proof for the nightly mycortex dream digest, 2026-10-12.
# Assertions: (A) dream file exact size + digest, (B) verbatim INDEX.md row,
# (C) both cited mycortex reads still return data AT rc=0, (D) five cited commits
# exist in history, (E) the digest's central count (0 stranded) read from the
# FROZEN fixture committed beside this script, not from the live peer-modified file.
# Self-contained: no assertion depends on uncommitted or peer state.
# Usage: bash docs/evidence/verify-dream-2026-10-12.sh
set -u
fail=0
say() { printf '%s\n' "$*"; }

DREAM="$HOME/brain/esther/dreams/2026-10-12.md"
INDEX="$HOME/brain/esther/dreams/INDEX.md"
MYCORTEX="$HOME/.hermes-cortex/scripts/mycortex"
REPO="$HOME/hermes-cortex"
FIXTURE="docs/evidence/fixtures/skill-drift-parity-freeze-2026-10-12.txt"
EXPECT_SIZE=4061
EXPECT_MD5=3a139c0106f752e546b8459dc7a38e0d

say "== A. dream file: exists, exact size, exact digest =="
if [ -f "$DREAM" ]; then
  size=$(wc -c < "$DREAM")
  md5=$(md5sum "$DREAM" | cut -d' ' -f1)
  say "   path=$DREAM"
  say "   size=$size (want $EXPECT_SIZE)"
  say "   md5=$md5 (want $EXPECT_MD5)"
  [ "$size" = "$EXPECT_SIZE" ] || { say "   FAIL - size mismatch"; fail=1; }
  [ "$md5" = "$EXPECT_MD5" ]   || { say "   FAIL - digest mismatch"; fail=1; }
else
  say "   FAIL - $DREAM does not exist"; fail=1
fi

say ""
say "== B. INDEX.md carries the appended 2026-10-12 row (verbatim) =="
want='2026-10-12 | The Window That Would Not Narrow | Cycle 12154 answered one false attribution six times by shrinking the claim (owner is 507eea1e, range touches nothing of theirs), then the peer landed its own lesson — stranded skills 1 → 0; the window is not a verdict about you.'
last=$(tail -1 "$INDEX")
if [ "$last" = "$want" ]; then
  say "   OK   - final line matches verbatim"
else
  say "   FAIL - final line is:"
  say "     $last"
  fail=1
fi
rows=$(grep -c '^2026-10-12 |' "$INDEX")
say "   rows dated 2026-10-12: $rows (want 1)"
[ "$rows" = "1" ] || { say "   FAIL - expected exactly one 2026-10-12 row"; fail=1; }

say ""
say "== C. cited mycortex reads return data, and the command itself exits 0 =="
list_out=$(python3 "$MYCORTEX" list -n 20 2>&1); list_rc=$?
list_n=$(printf '%s\n' "$list_out" | grep -c 'hermes-cortex\|esther')
say "   mycortex list -n 20 -> rc=$list_rc, $list_n pages"
[ "$list_rc" -eq 0 ] || { say "   FAIL - list exited rc=$list_rc"; fail=1; }
[ "$list_n" -ge 20 ] || { say "   FAIL - list returned fewer than 20 pages"; fail=1; }

srch_out=$(python3 "$MYCORTEX" search "stranded skill drift deployed" --limit 3 2>&1); srch_rc=$?
top=$(printf '%s\n' "$srch_out" | head -1)
say "   mycortex search -> rc=$srch_rc, top hit: $top"
[ "$srch_rc" -eq 0 ] || { say "   FAIL - search exited rc=$srch_rc"; fail=1; }
printf '%s' "$top" | grep -q '0\.99' || { say "   FAIL - search returned no ranked hit"; fail=1; }

say ""
say "== D. the git evidence the digest cites is real =="
cd "$REPO" || { say "   FAIL - $REPO missing"; exit 1; }
for sha in d2ab1cb6 d91f3a61 d8373daa 1a57f7a0 507eea1e; do
  subj=$(git log --format='%s' -1 "$sha" 2>/dev/null)
  say "   $sha  ${subj:-<NOT FOUND>}"
  [ -n "$subj" ] || { say "     FAIL - $sha not in history"; fail=1; }
done

say ""
say "== E. the digest's central count, read from the FROZEN fixture =="
if [ -f "$FIXTURE" ]; then
  stranded=$(grep 'Deployed-only files (stranded)' "$FIXTURE" | grep -o '[0-9]\+')
  say "   fixture=$FIXTURE"
  say "   stranded=$stranded (want 0)"
  [ "${stranded:-x}" = "0" ] || { say "   FAIL - fixture stranded count is not 0"; fail=1; }
else
  say "   FAIL - fixture $FIXTURE missing (assertion cannot rely on peer state)"; fail=1
fi

say ""
if [ "$fail" -eq 0 ]; then
  say "RESULT: 5/5 assertion groups PASS, exit 0"
  say "RESULT: PASS - all assertions held"
else
  say "RESULT: FAIL - one or more assertions did not hold (see named FAIL lines above)"
fi
exit "$fail"
