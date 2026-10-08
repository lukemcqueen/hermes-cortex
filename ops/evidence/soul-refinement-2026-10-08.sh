#!/usr/bin/env bash
# Re-runnable evidence for the soul-refinement cycle 11698 (2026-10-08).
#
# Two lessons were added to repo-source skills, plus a saved review file listing
# the deployed-only lessons that the cron CANNOT deploy from its checkout.
# Run from the repo root:  bash ops/evidence/soul-refinement-2026-10-08.sh
#
# Every claim the cycle note makes about gates is reproduced here, with exit codes.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
REPO="$PWD"

hr() { printf '\n===== %s =====\n' "$1"; }
chk() { # name expected actual
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s = %s\n' "$1" "$3"
  else printf 'FAIL  %s: expected %s got %s\n' "$1" "$2" "$3"; fi
}

hr "revision"
git log --oneline -1
echo "HEAD=$(git rev-parse HEAD)"
echo "origin/main=$(git rev-parse origin/main)"

hr "1. adversarial A2 gate — the two changed skill files"
for f in skills/devops/orch-skill-lifecycle/SKILL.md skills/devops/psql-automation/SKILL.md; do
  python3 ops/scripts/quality/adversarial-verify.py --file "$f" --level A2 --gate \
    > /tmp/adv.out 2>&1
  rc=$?
  chk "A2 gate $f" 0 "$rc"
  grep -E 'GATE_PASSED|GATE_FAILED|finding\(s\)' /tmp/adv.out | tail -2
done

hr "2. skills manifest is fresh (uses the PyYAML-capable resolver)"
bash ops/scripts/manage/gen-skills-manifest.sh --check
chk "manifest --check" 0 "$?"

hr "3. change-validate on the staged/committed set"
git diff --cached --name-only | sed 's/^/  staged: /'
bash ops/scripts/change-validate.sh > /tmp/cv.out 2>&1
chk "change-validate exit" 0 "$?"
tail -2 /tmp/cv.out

hr "4. the drift count claimed in orch-skill-lifecycle: TOTAL commits touching skills/ in 7d"
git log --format=%h --since="7 days ago" -- skills/ | wc -l
echo "-- narrowed to commits whose message says 'skill' or 'drift':"
git log --format=%h --since="7 days ago" -- skills/ \
  | xargs -r git log --no-walk --format='%h %s' \
  | grep -icE 'drift|skills?' || true
echo "-- the 6 SHAs the note itself cites:"
git log --no-walk --format='%h %s' badbc960 de5f058c 56c3a825 55173ab5 3123e26a 8bd82dcb 2>/dev/null | wc -l

hr "5. the psql-automation rc=1 claim, reproduced under NoNewPrivileges"
: > /tmp/nnp.sg 2>/dev/null
setpriv --no-new-privs -- sg docker -c "echo marker" > /tmp/nnp.sg 2>&1
rc_sg=$?
printf 'setpriv --no-new-privs -- sg docker -c "echo marker"  -> rc=%s\n' "$rc_sg"
cat /tmp/nnp.sg | head -2
setpriv --no-new-privs -- docker exec nosuchcontainer true >/dev/null 2>&1
printf 'setpriv --no-new-privs -- docker exec <c> true        -> rc=%s (docker itself works; the sg wrapper is the refusal)\n' "$?"
echo "-- the false-negative shape the note describes:"
( setpriv --no-new-privs -- sg docker -c "echo present" | grep -q present ) \
  && echo "grep found the marker" || echo "grep reported ABSENT (command never ran: rc=$rc_sg)"

hr "6. deployed-only lessons saved for review (count of stranded paths)"
python3 ops/scripts/manage/check-skill-drift-parity.py 2>/dev/null \
  | grep -E '^\| (Deployed-only files|Files in sync)' || true
echo "saved file: $(wc -l < docs/evidence/saved-deployed-skill-lessons-2026-10-08.txt) lines"

hr "done"
