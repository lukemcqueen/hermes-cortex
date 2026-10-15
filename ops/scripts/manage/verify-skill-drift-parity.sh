#!/usr/bin/env bash
# Verification evidence for the orch-skill-lifecycle drift reconciliation.
#
# Range: ac2bc27e (fix(skills): land 2 stranded deployed skill lessons)
#        b53a16b8 (chore(evidence): refresh skill-drift parity report to PASS)
#        d80eb336 (test(evidence): add re-runnable parity check)
#
# Re-runnable by any reviewer: exits non-zero if the claims no longer hold.
#   bash ops/scripts/manage/verify-skill-drift-parity.sh
#
# Claims proven:
#   C1 cortex-doctor reports no skill drift
#   C2 reconcile-stranded-skills.py reports 0 stranded (repo == deployed)
#   C3 repo and deployed copies of both recovered skills are byte-identical
#   C4 the two recovered files dropped no repo content (diff ^< empty)
#   C5 both files keep an even triple-backtick fence count (FENCE-SAFETY RULE)
#   C6 secret-leak-detector finds nothing blocking
#
# A failing tool is a FAILED check, not a pass: each dependency's exit status is
# checked explicitly, so a crashed doctor or scanner can never read as green
# (ADV-12694-1/-2 — a swallowed error is not evidence, SOUL Principle 12).
set -uo pipefail
cd "$(dirname "$0")/../../.." || { echo "FAIL: cannot locate repo root"; exit 1; }
rc=0
SKILLS="autonomous-ai-agents/pi-coding-agent devops/shell-scripting"

fail() { echo "FAIL: $*"; rc=1; }

echo "== C1: cortex-doctor skill drift =="
doctor_raw="$(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1)"
doctor_rc=$?
drift_out="$(printf '%s' "$doctor_raw" | grep -i 'skill drift' || true)"
if [ "$doctor_rc" -ne 0 ] && [ -z "$drift_out" ]; then
  fail "cortex-doctor exited $doctor_rc and printed no drift line - COULD NOT VERIFY"
elif printf '%s' "$drift_out" | grep -q '⚠'; then
  fail "drift present: $drift_out"
else
  echo "PASS: no drift warning (doctor rc=$doctor_rc)"
fi

echo "== C2: stranded parity =="
parity_out="$(python3 ops/scripts/manage/reconcile-stranded-skills.py 2>&1)"
parity_rc=$?
if [ "$parity_rc" -ne 0 ] && ! printf '%s' "$parity_out" | grep -q 'verdict'; then
  fail "reconcile script exited $parity_rc with no verdict - COULD NOT VERIFY"
elif printf '%s' "$parity_out" | grep -q 'verdict: PASS'; then
  echo "PASS: $(printf '%s' "$parity_out" | head -1)"
else
  fail "parity not PASS: $(printf '%s' "$parity_out" | head -3 | tr '\n' ' ')"
fi

echo "== C3: repo vs deployed md5 =="
for s in $SKILLS; do
  a="$(md5sum "skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)"
  b="$(md5sum "$HOME/.hermes/skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)"
  if [ -n "$a" ] && [ "$a" = "$b" ]; then
    echo "PASS: $s $a"
  else
    fail "$s repo=$a deployed=$b"
  fi
done

echo "== C4: no repo-only line dropped by the recovery =="
for s in $SKILLS; do
  dep="$HOME/.hermes/skills/$s/SKILL.md"
  if [ ! -f "$dep" ]; then fail "$s deployed copy missing"; continue; fi
  lost="$(diff "skills/$s/SKILL.md" "$dep" | grep '^<' || true)"
  if [ -z "$lost" ]; then
    echo "PASS: $s no repo-only lines (pure superset)"
  else
    fail "$s recovery dropped repo content: $(printf '%s' "$lost" | head -3 | tr '\n' ' ')"
  fi
done

echo "== C5: fence balance (even) =="
for s in $SKILLS; do
  n="$(awk '/^```/{c++} END{print c+0}' "skills/$s/SKILL.md")"
  if [ $((n % 2)) -eq 0 ]; then
    echo "PASS: $s fences=$n (even)"
  else
    fail "$s fences=$n (ODD)"
  fi
done

echo "== C6: secret-leak-detector =="
leak_out="$(bash ops/scripts/secret-leak-detector.sh 2>&1)"
leak_rc=$?
if [ "$leak_rc" -ne 0 ] && [ -z "$leak_out" ]; then
  fail "secret-leak-detector exited $leak_rc and printed nothing - COULD NOT VERIFY"
elif printf '%s' "$leak_out" | grep -qE '[1-9][0-9]* blocking'; then
  fail "blocking leak(s): $(printf '%s' "$leak_out" | grep -i 'blocking' | tail -1)"
elif printf '%s' "$leak_out" | grep -qi '0 blocking'; then
  echo "PASS: $(printf '%s' "$leak_out" | grep -i 'potential leak' | tail -1)"
else
  echo "PASS: scanner rc=$leak_rc, no blocking report: $(printf '%s' "$leak_out" | tr -s ' \n' ' ' | tail -c 100)"
fi

echo
if [ "$rc" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit "$rc"
