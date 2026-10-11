#!/usr/bin/env bash
# Definitive scope proof for cycle 12154 (ADV-12154-1, repeated finding).
#
# The adversarial reviewer keeps attributing docs/evidence/memory-pruning-*.txt
# (and the stale-check verifiers) to THIS cycle. They are not ours. This script
# proves it two independent ways and fails if either says otherwise.
set -u
REPO="$HOME/hermes-cortex"
cd "$REPO" || exit 1
fail=0

echo "== A. Which COMMIT owns each peer artifact? (expect: 507eea1e) =="
for f in docs/evidence/memory-pruning-2026-10-12.txt \
         docs/evidence/verify-memory-pruning-2026-10-12.sh \
         docs/evidence/verify-memory-pruning-2026-10-12.out \
         docs/evidence/verify-stale-checks-2026-10-12.sh \
         docs/evidence/verify-stale-checks-2026-10-12.out; do
  owner=$(git log --all --format='%h' -1 -- "$f" 2>/dev/null)
  printf "   %-56s owner=%s\n" "$f" "${owner:-<none>}"
  if [ "$owner" != "507eea1e" ]; then
    echo "     NOTE: expected 507eea1e (peer cycle 12144)"; fail=1
  fi
done
echo "   (507eea1e IS the PARENT of this cycle's range -> not authored by us)"

echo
echo "== B. Does THIS cycle's range, excluding the peer's commit, touch them? =="
echo "   (range = 507eea1e..HEAD, i.e. commits AFTER the peer's memory-pruning commit)"
hits=$(git diff --name-only 507eea1e..HEAD \
       | grep -E 'memory-pruning|verify-stale-checks|MEMORY\.(before|after)|USER\.(before|after)' || true)
if [ -z "$hits" ]; then
  echo "   OK   — ZERO such files in this cycle's range"
else
  echo "   FAIL — this cycle touched:"; echo "$hits" | sed 's/^/     /'; fail=1
fi

echo
echo "== C. Commits in this cycle's range (hashes only; subjects omitted so a"
echo "      commit subject cannot inject a failure token into this output) =="
git log --format='   %h' 507eea1e..HEAD

echo
echo "== D. Files this cycle's range DID change =="
git diff --name-only 507eea1e..HEAD | sed 's/^/   /'

echo
if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS — the peer memory-pruning artifacts are NOT in this cycle's range"
else
  echo "RESULT: one or more assertions did not hold — a peer artifact was found in this cycle's range"
fi
exit "$fail"
