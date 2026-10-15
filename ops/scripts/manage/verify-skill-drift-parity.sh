#!/usr/bin/env bash
# Verification evidence for the orch-skill-lifecycle drift reconciliation.
#
# Range: ac2bc27e (fix(skills): land 2 stranded deployed skill lessons)
#        b53a16b8 (chore(evidence): refresh skill-drift parity report to PASS)
#        d80eb336 (test(evidence): add re-runnable parity check)
#        146f78e4 (fix(evidence): stop the parity check swallowing tool errors)
#
# Re-runnable by any reviewer: exits non-zero if the claims no longer hold.
#   bash ops/scripts/manage/verify-skill-drift-parity.sh
#
# Claims proven:
#   C1 cortex-doctor ran AND reports no skill drift
#   C2 reconcile-stranded-skills.py ran AND reports 0 stranded (repo == deployed)
#   C3 repo and deployed copies of both recovered skills are byte-identical
#   C4 the two recovered files dropped no repo content (diff ^< empty)
#   C5 both files keep an even triple-backtick fence count (FENCE-SAFETY RULE)
#   C6 secret-leak-detector ran AND finds nothing blocking
#
# ERROR POLICY (SOUL Principle 12 — never swallow errors).
# A dependency whose run is NOT EVIDENT is a FAILED check, never a pass. Evidence
# of a run is checked per tool, because exit codes alone are ambiguous here:
#   - cortex-doctor exits 1 whenever ANY warning exists, so rc alone cannot
#     separate "ran fine, warnings present" from "crashed"; it must have emitted
#     its per-check output (>= MIN_DOCTOR_LINES lines) or we say COULD NOT VERIFY.
#   - secret-leak-detector exits 0 in the clean case; ANY non-zero exit is
#     treated as COULD NOT VERIFY (its report text is what we actually judge).
#   - reconcile-stranded-skills.py must print a verdict line.
set -uo pipefail
cd "$(dirname "$0")/../../.." || { echo "FAIL: cannot locate repo root"; exit 1; }
rc=0
SKILLS="autonomous-ai-agents/pi-coding-agent devops/shell-scripting"
MIN_DOCTOR_LINES=100

fail() { echo "FAIL: $*"; rc=1; }

echo "== C1: cortex-doctor ran, and reports no skill drift =="
doctor_raw="$(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1)"
doctor_rc=$?
doctor_lines="$(printf '%s' "$doctor_raw" | grep -cE '^[[:space:]]*(✅|⚠️|❌|➖)' || true)"
if [ "$doctor_lines" -lt "$MIN_DOCTOR_LINES" ]; then
  fail "cortex-doctor emitted only $doctor_lines check lines (rc=$doctor_rc) - COULD NOT VERIFY"
else
  drift_out="$(printf '%s' "$doctor_raw" | grep -i 'skill drift' || true)"
  if printf '%s' "$drift_out" | grep -q '⚠'; then
    fail "drift present: $drift_out"
  else
    echo "PASS: no drift warning (doctor rc=$doctor_rc, $doctor_lines check lines)"
  fi
fi

echo "== C2: stranded parity =="
parity_out="$(python3 ops/scripts/manage/reconcile-stranded-skills.py 2>&1)"
parity_rc=$?
if ! printf '%s' "$parity_out" | grep -qE 'verdict: (PASS|FAIL)'; then
  fail "reconcile script (rc=$parity_rc) printed no verdict line - COULD NOT VERIFY"
elif printf '%s' "$parity_out" | grep -q 'verdict: PASS'; then
  echo "PASS: $(printf '%s' "$parity_out" | head -1)"
else
  fail "parity not PASS: $(printf '%s' "$parity_out" | head -3 | tr '\n' ' ')"
fi

echo "== C3: repo vs deployed md5 =="
for s in $SKILLS; do
  repo="skills/$s/SKILL.md"
  dep="$HOME/.hermes/skills/$s/SKILL.md"
  if [ ! -f "$repo" ]; then fail "$s repo copy missing: $repo"; continue; fi
  if [ ! -f "$dep" ]; then fail "$s deployed copy missing: $dep"; continue; fi
  a="$(md5sum "$repo" | cut -d' ' -f1)"
  b="$(md5sum "$dep" | cut -d' ' -f1)"
  if [ "$a" = "$b" ]; then
    echo "PASS: $s $a"
  else
    fail "$s repo=$a deployed=$b"
  fi
done

echo "== C4: no repo-only line dropped by the recovery =="
for s in $SKILLS; do
  repo="skills/$s/SKILL.md"
  dep="$HOME/.hermes/skills/$s/SKILL.md"
  if [ ! -f "$repo" ]; then fail "$s repo copy missing, cannot diff"; continue; fi
  if [ ! -f "$dep" ]; then fail "$s deployed copy missing, cannot diff"; continue; fi
  # capture stderr too: a diff that cannot run must not read as "no deletions"
  diff_full="$(diff "$repo" "$dep" 2>&1)"
  diff_rc=$?
  if [ "$diff_rc" -gt 1 ]; then
    fail "$s diff exited $diff_rc - COULD NOT VERIFY: $(printf '%s' "$diff_full" | head -2 | tr '\n' ' ')"
    continue
  fi
  lost="$(printf '%s' "$diff_full" | grep '^<' || true)"
  if [ -z "$lost" ]; then
    echo "PASS: $s no repo-only lines (pure superset)"
  else
    fail "$s recovery dropped repo content: $(printf '%s' "$lost" | head -3 | tr '\n' ' ')"
  fi
done

echo "== C5: fence balance (even) =="
for s in $SKILLS; do
  repo="skills/$s/SKILL.md"
  if [ ! -f "$repo" ]; then fail "$s repo copy missing"; continue; fi
  n="$(awk '/^```/{c++} END{print c+0}' "$repo")"
  if [ $((n % 2)) -eq 0 ]; then
    echo "PASS: $s fences=$n (even)"
  else
    fail "$s fences=$n (ODD)"
  fi
done

echo "== C6: secret-leak-detector ran, and finds nothing blocking =="
leak_out="$(bash ops/scripts/secret-leak-detector.sh 2>&1)"
leak_rc=$?
# Measured behaviour: rc=0 with EMPTY output is the clean case; rc=0 with a
# report is judged on the blocking count; any non-zero rc is COULD NOT VERIFY.
if [ "$leak_rc" -ne 0 ]; then
  fail "secret-leak-detector exited $leak_rc - COULD NOT VERIFY: $(printf '%s' "$leak_out" | tr -s ' \n' ' ' | tail -c 120)"
elif printf '%s' "$leak_out" | grep -qE '[1-9][0-9]* blocking'; then
  fail "blocking leak(s): $(printf '%s' "$leak_out" | grep -i 'blocking' | tail -1)"
elif [ -z "$leak_out" ]; then
  echo "PASS: scanner rc=0, silent (no leak report)"
elif printf '%s' "$leak_out" | grep -qi 'potential leak'; then
  echo "PASS: $(printf '%s' "$leak_out" | grep -i 'potential leak' | tail -1)"
else
  fail "secret-leak-detector rc=0 but printed an unrecognised report - COULD NOT VERIFY: $(printf '%s' "$leak_out" | tr -s ' \n' ' ' | tail -c 120)"
fi

echo
if [ "$rc" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit "$rc"
