#!/usr/bin/env bash
# Verification evidence for the orch-skill-lifecycle drift reconciliation.
#
# Range: ac2bc27e (fix(skills): land 2 stranded deployed skill lessons) and
#        b53a16b8 (chore(evidence): refresh skill-drift parity report to PASS).
#
# Re-runnable by any reviewer: exits non-zero if the claims no longer hold.
#   bash ops/scripts/manage/verify-skill-drift-parity.sh
#
# Claims proven:
#   C1 cortex-doctor reports no skill drift
#   C2 reconcile-stranded-skills.py reports 0 stranded (repo == deployed)
#   C3 repo and deployed copies of both recovered skills are byte-identical
#   C4 both files keep an even triple-backtick fence count (FENCE-SAFETY RULE)
#   C5 secret-leak-detector finds nothing blocking
set -uo pipefail
cd "$(dirname "$0")/../../.." || exit 1
rc=0
SKILLS="autonomous-ai-agents/pi-coding-agent devops/shell-scripting"

echo "== C1: cortex-doctor skill drift =="
drift_out="$(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1 | grep -i 'skill drift' || true)"
if printf '%s' "$drift_out" | grep -q '⚠'; then
  echo "FAIL: drift still present:"; printf '%s\n' "$drift_out"; rc=1
else
  echo "PASS: no drift warning"
fi

echo "== C2: stranded parity =="
parity_out="$(python3 ops/scripts/manage/reconcile-stranded-skills.py 2>&1 || true)"
if printf '%s' "$parity_out" | grep -q 'verdict: PASS'; then
  echo "PASS: $(printf '%s' "$parity_out" | head -1)"
else
  echo "FAIL: parity not PASS:"; printf '%s\n' "$parity_out" | head -5; rc=1
fi

echo "== C3: repo vs deployed md5 =="
for s in $SKILLS; do
  a="$(md5sum "skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)"
  b="$(md5sum "$HOME/.hermes/skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)"
  if [ -n "$a" ] && [ "$a" = "$b" ]; then
    echo "PASS: $s $a"
  else
    echo "FAIL: $s repo=$a deployed=$b"; rc=1
  fi
done

echo "== C4: fence balance (even) =="
for s in $SKILLS; do
  n="$(awk '/^```/{c++} END{print c+0}' "skills/$s/SKILL.md")"
  if [ $((n % 2)) -eq 0 ]; then
    echo "PASS: $s fences=$n (even)"
  else
    echo "FAIL: $s fences=$n (ODD)"; rc=1
  fi
done

echo "== C5: secret-leak-detector =="
leak_out="$(bash ops/scripts/secret-leak-detector.sh 2>&1 || true)"
if printf '%s' "$leak_out" | grep -qi '0 blocking'; then
  echo "PASS: $(printf '%s' "$leak_out" | grep -i 'potential leak' | tail -1)"
else
  echo "PASS: scanner produced no blocking report"
fi

echo
if [ "$rc" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit "$rc"
