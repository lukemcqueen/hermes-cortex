#!/usr/bin/env bash
# Verify the 2026-10-12 skill-lifecycle drift-sync for 3 skills (commit d2ab1cb6).
# Reproduces: superset/no-deletion, fence balance, A2 gate, secret-leak, md5, doctor drift.
# Usage: bash verify-skill-drift-sync-2026-10-12.sh
set -u
REPO=~/hermes-cortex
DEPLOY=~/.hermes/skills
RC=0

echo "=== Superset check: deployed must be SUPERSET of repo (no 'd'-deletions) ==="
for s in fleet-commands governance-closeout loop-governance; do
  changes=$(diff "$REPO/skills/devops/$s/SKILL.md" "$DEPLOY/devops/$s/SKILL.md" | grep -E '^[0-9,]+d[0-9]' | wc -l)
  echo "$s deletions-of-repo-content: $changes (want 0)"
  [ "$changes" -eq 0 ] || RC=1
done

echo "=== Fence balance (even = balanced), both sides ==="
for s in fleet-commands governance-closeout loop-governance; do
  for side in "$REPO/skills/devops/$s/SKILL.md" "$DEPLOY/devops/$s/SKILL.md"; do
    c=$(grep -c '^```' "$side")
    echo "$side: fences=$c (want even)"
    [ $((c % 2)) -eq 0 ] || RC=1
  done
done

echo "=== A2 adversarial gate on repo copies ==="
cd "$REPO" || exit 2
for s in fleet-commands governance-closeout loop-governance; do
  out=$(python3 ops/scripts/quality/adversarial-verify.py --file skills/devops/$s/SKILL.md --level A2 --gate 2>&1)
  echo "$s: $(echo "$out" | grep -c 'GATE_PASSED') GATE_PASSED (want 1)"
  echo "$out" | grep -q 'GATE_PASSED' || RC=1
done

echo "=== Secret-leak detector (expect rc=0) ==="
bash ops/scripts/secret-leak-detector.sh >/dev/null 2>&1
echo "secret-leak rc=$?"
[ $? -eq 0 ] || RC=1

echo "=== md5(matcher): repo == deployed after sync ==="
for s in fleet-commands governance-closeout loop-governance; do
  a=$(md5sum < "$REPO/skills/devops/$s/SKILL.md")
  b=$(md5sum < "$DEPLOY/devops/$s/SKILL.md")
  [ "$a" = "$b" ] && echo "$s: MATCH" || { echo "$s: MISMATCH"; RC=1; }
done

echo "=== Doctor skill-drift section (expect skill drift clear) ==="
python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1 | grep -iE 'skill drift|✅ Skill' || echo "(no drift lines)"

echo "=== VERDICT ==="
if [ "$RC" -eq 0 ]; then echo "PASS — all checks green"; else echo "FAIL — see above"; fi
exit $RC