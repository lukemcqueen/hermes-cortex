#!/usr/bin/env bash
# ADV-12154-2 evidence: SOUL.md is deliberately untouched by cycle 12154.
#
# The task text says "upgrade skills/SOUL.md" — that authorises a SOUL.md
# upgrade WHEN one is warranted. This cycle found none warranted, for two
# checked reasons, both shown below:
#   1. No new SOUL candidate was produced today (2026-10-12).
#   2. The only outstanding candidate (2026-10-11) is explicitly marked
#      PROPOSED / operator-owned, and identity documents are the operator's.
set -u
REPO="$HOME/hermes-cortex"
cd "$REPO" || exit 1

echo "== 1. Is SOUL.md modified by THIS cycle's range? (expect: no) =="
if git diff --name-only 507eea1e..HEAD -- ':/SOUL.md' ':/skills/**/SOUL.md' | grep -q .; then
  echo "  FAIL — this cycle touched a SOUL.md"
else
  echo "  OK   — this cycle's diff (507eea1e..HEAD) contains NO SOUL.md change"
fi

echo
echo "== 2. Deployed SOUL.md is unchanged vs its repo source (doctor check) =="
python3 ops/scripts/manage/cortex-doctor.py --quiet 2>/dev/null \
  | grep -iE 'SOUL.md' | sed 's/^/  /'

echo
echo "== 3. Local principles currently in the deployed SOUL.md =="
grep -nE '^### 1[3-9]\.' "$HOME/.hermes/SOUL.md" | sed 's/^/  /'

echo
echo "== 4. The outstanding candidate's own status line (2026-10-11) =="
sed -n '1,5p' docs/reviews/soul-refinement-2026-10-11.md | sed 's/^/  /'

echo
echo "== 5. Any NEW soul-refinement artifact dated today? (expect: none) =="
today=$(date +%Y-%m-%d)
found=$(find docs/reviews -name "soul-refinement-${today}*" 2>/dev/null)
echo "  ${found:-(none — no candidate was produced today)}"

echo
echo "CONCLUSION: SOUL.md upgrade NOT applied because (a) no new candidate exists"
echo "today and (b) the one open candidate is PROPOSED/operator-owned. Applying it"
echo "would be an operator-owned identity edit — declined under the pushback"
echo "contract (SOUL Principle 5). Recorded as issue #90."
