#!/usr/bin/env bash
# Re-verify the review-provenance enforcement: the gate's precision, its both-directions tests,
# the doctor wiring, and the live result on this tree.
#
#   bash docs/evidence/review-provenance-verify.sh [repo-path]
#
# Read-only: it runs the checker (which only reads) and the doctor, and writes nothing to the repo.
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" || { echo "no such repo: $REPO"; exit 2; }
CHECK=ops/scripts/quality/review-provenance-check.py
FAILED=0

exec > >(sed "s|$HOME|~|g") 2>&1
step() { echo; echo "--- $*"; }

step "1. contract tests: both directions, the third outcome, and the discriminator's precision"
out=$(bash tests/run-tests.sh tests/test_review_provenance_check.py 2>&1); rc=$?
printf '%s\n' "$out" | grep -E "passed|failed" | tail -2
[ "$rc" -eq 0 ] && echo "PASS  rc=0" || { echo "FAIL  rc=$rc"; FAILED=1; }

step "2. the gate on THIS tree (must be clean, or the doctor FAILs and blocks every push here)"
python3 "$CHECK" --repo . ; grc=$?
echo "gate rc=$grc"
[ "$grc" -eq 0 ] && echo "PASS" || { echo "FAIL"; FAILED=1; }

step "3. a PLANTED violation must be caught (probing the gate, not just reading it)"
T=$(mktemp -d); mkdir -p "$T/docs/evidence"
printf '# Independent review\n\nmodel: some-model\n\nThe code is fine.\n' \
  > "$T/docs/evidence/notes-without-provenance.md"
python3 "$CHECK" --repo "$T" --db "$T/none.db" > "$T/out.txt" 2>&1; prc=$?
echo "planted rc=$prc (expect 1)"
grep -m1 "no provenance" "$T/out.txt" | sed 's/^/   /' || true
[ "$prc" -eq 1 ] && echo "PASS  the gate notices an undeclared review" || { echo "FAIL"; FAILED=1; }
rm -rf "$T"

step "4. the doctor check is WIRED (enforcement point: a FAIL here blocks every push)"
# The doctor's EXIT CODE is not the check's verdict (it exits non-zero for warnings too), and the
# level is rendered as a symbol, so match the NAME and read the annotation beside it.
doc_out=$(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1); drc=$?
echo "doctor rc=$drc  (host-wide status; NOT this check's verdict — see the annotated line)"
printf '%s\n' "$doc_out" | grep -i "Review provenance" | sed 's/^/   /'
printf '%s\n' "$doc_out" | grep -qi "Review provenance" && echo "PASS  the check runs in the doctor" || { echo "FAIL  not wired"; FAILED=1; }
printf '%s\n' "$doc_out" | grep -iE "(❌|⚠️)" | head -5 | sed 's/^/   other: /' || true

echo
if [ "$FAILED" -eq 0 ]; then echo "ALL CLAIMS RE-VERIFIED (rc=0)"; else echo "SOME CLAIMS FAILED (rc=1)"; fi
exit "$FAILED"
