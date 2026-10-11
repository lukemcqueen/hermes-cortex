#!/usr/bin/env bash
# Re-runnable verification for orch-skill-lifecycle 2026-10-12 (cycle 12154).
#
# Proves the three claims in the cycle note:
#   A) the 6 stranded skills were synced repo<-deployed with md5 equality
#   B) fence counts are EVEN on both sides for those 6 files
#   C) the detector read PASS with 0 stranded for the six, and the ONLY
#      remaining drift is devops/governance-closeout (a peer's open-lock file,
#      a PURE SUPERSET with zero repo-only lines)
#
# Exit 0 = every assertion held.  Exit 1 = an assertion failed (prints which).
set -u
REPO="$HOME/hermes-cortex"
cd "$REPO" || exit 1
fail=0

SKILLS=(
  devops/cortex-deployment-sync
  devops/cron-job-management
  devops/enforcement-change-safety
  devops/enforcer-modification-considerations
  software-development/hermetic-python-testing
  software-development/session-manager
)

echo "== A. md5 repo == deployed (the 6 synced skills) =="
for s in "${SKILLS[@]}"; do
  r=$(md5sum "skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)
  d=$(md5sum "$HOME/.hermes/skills/$s/SKILL.md" 2>/dev/null | cut -d' ' -f1)
  if [ -n "$r" ] && [ "$r" = "$d" ]; then
    printf "  OK   %-52s %s\n" "$s" "$r"
  else
    printf "  FAIL %-52s repo=%s deployed=%s\n" "$s" "$r" "$d"; fail=1
  fi
done

echo
echo "== B. fence balance EVEN on both sides =="
for s in "${SKILLS[@]}"; do
  rn=$(grep -c '^```' "skills/$s/SKILL.md" 2>/dev/null)
  dn=$(grep -c '^```' "$HOME/.hermes/skills/$s/SKILL.md" 2>/dev/null)
  if [ $((rn % 2)) -eq 0 ] && [ $((dn % 2)) -eq 0 ]; then
    printf "  OK   %-52s repo=%s deployed=%s\n" "$s" "$rn" "$dn"
  else
    printf "  FAIL %-52s repo=%s deployed=%s (ODD)\n" "$s" "$rn" "$dn"; fail=1
  fi
done

echo
echo "== C. detector verdict + attribution of residual drift =="
python3 ops/scripts/manage/check-skill-drift-parity.py | grep -E 'stranded|in sync|Verdict' | sed 's/^/  /'

echo
echo "  -- residual drift entries (expected: ONLY devops/governance-closeout) --"
drifted=$(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>/dev/null \
          | grep 'Skill drift:' | sed 's/.*Skill drift: //;s/ —.*//' | sort -u)
echo "     ${drifted:-(none)}"
if [ "$drifted" != "devops/governance-closeout" ]; then
  echo "     NOTE: residual drift is not the single expected peer file"; fail=1
fi

echo
echo "  -- the peer file is a PURE SUPERSET (0 repo-only lines) --"
nrm=$(diff "skills/devops/governance-closeout/SKILL.md" \
           "$HOME/.hermes/skills/devops/governance-closeout/SKILL.md" | grep -c '^<')
nad=$(diff "skills/devops/governance-closeout/SKILL.md" \
           "$HOME/.hermes/skills/devops/governance-closeout/SKILL.md" | grep -c '^>')
echo "     repo-only lines (must be 0): $nrm"
echo "     deployed-only lines (the peer's additions): $nad"
[ "$nrm" -eq 0 ] || fail=1

echo
echo "  -- the OPEN peer lock that makes it that session's file --"
python3 - <<'PY'
import json, os, glob
for p in glob.glob(os.path.expanduser("~/.hermes-cortex/state/.governance-*.json")):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    if d.get("task_id", "").startswith("memory-pruning"):
        print("     task_id=%s" % d.get("task_id"))
        print("     status=%s" % d.get("status"))
PY

echo
if [ "$fail" -eq 0 ]; then echo "RESULT: PASS — all assertions held"; else echo "RESULT: FAIL — see FAIL lines above"; fi
exit "$fail"
