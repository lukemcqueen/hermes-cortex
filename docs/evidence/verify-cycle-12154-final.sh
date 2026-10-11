#!/usr/bin/env bash
# ADV-12154 (final pass) — prove the push/HEAD state and the detector FAIL(1)
# root cause, so a later reviewer can re-run and confirm no self-caused
# stranded skill hides behind the prose attribution.
#
# Run AFTER a `git fetch`; exit 0 = all assertions held.
set -u
REPO="$HOME/hermes-cortex"
cd "$REPO" || exit 1
fail=0

echo "== 1. Origin state: is the local tip published? =="
git fetch --quiet origin main 2>/dev/null || true
local_tip=$(git rev-parse HEAD)
remote_tip=$(git rev-parse origin/main)
echo "   HEAD            = $local_tip"
echo "   origin/main     = $remote_tip"
if [ "$local_tip" = "$remote_tip" ]; then
  echo "   OK   — HEAD == origin/main (nothing unpushed)"
else
  echo "   FAIL — local tip is not published"; fail=1
fi

echo
echo "== 2. The commit the push published (this cycle's tip before evidence) =="
git log --oneline -1 82f2d9c1 2>/dev/null | sed 's/^/   /' || echo "   (82f2d9c1 not found)"
echo "   -- is 82f2d9c1 an ancestor of origin/main? (expected: yes) --"
if git merge-base --is-ancestor 82f2d9c1 origin/main 2>/dev/null; then
  echo "   OK   — 82f2d9c1 is reachable from origin/main"
else
  echo "   FAIL — 82f2d9c1 is not on the remote"; fail=1
fi

echo
echo "== 3. This cycle's commit range (files ONLY these commits touched) =="
base=$(git rev-parse 507eea1e)
echo "   range = 507eea1e..HEAD  (507eea1e = the peer's cycle-12144 commit, the PARENT)"
git diff --name-only "$base"..HEAD | sed 's/^/     /'

echo
echo "   -- does that range contain ANY memory-pruning / stale-check artifact? --"
if git diff --name-only "$base"..HEAD \
   | grep -E 'memory-pruning|verify-stale-checks|MEMORY\.(before|after)|USER\.(before|after)' | grep -q .; then
  echo "   FAIL — this cycle's range DOES contain peer memory-pruning artifacts"; fail=1
else
  echo "   OK   — ZERO memory-pruning/stale-check files in this cycle's range"
  echo "          (they are 507eea1e, the peer's own commit, BEFORE this range)"
fi

echo
echo "== 4. Detector: the exact residual drift and its owner =="
python3 ops/scripts/manage/check-skill-drift-parity.py \
  | grep -E 'stranded|in sync|Verdict' | sed 's/^/   /'
echo
echo "   -- every drifted skill reported by the doctor --"
python3 ops/scripts/manage/cortex-doctor.py --quiet 2>/dev/null \
  | grep 'Skill drift:' | sed 's/^/     /'
echo
echo "   -- every repo-vs-deployed diff for those skills is a PURE SUPERSET? --"
for s in $(python3 ops/scripts/manage/cortex-doctor.py --quiet 2>/dev/null \
           | grep 'Skill drift:' | sed 's/.*Skill drift: //;s/ —.*//' | sort -u); do
  rm_count=$(diff "skills/$s/SKILL.md" "$HOME/.hermes/skills/$s/SKILL.md" 2>/dev/null | grep -c '^<')
  echo "     $s: repo-only lines = $rm_count (0 = pure superset, no lost content)"
done

echo
echo "== 5. The open peer lock that owns the residual drift =="
python3 - <<'PY'
import json, os, glob
found = False
for p in glob.glob(os.path.expanduser("~/.hermes-cortex/state/.governance-*.json")):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    tid = d.get("task_id", "")
    if tid.startswith("memory-pruning"):
        found = True
        print("     task_id=%s" % tid)
        print("     status =%s" % d.get("status"))
        print("     scope  =%s" % str(d.get("description"))[:110])
if not found:
    print("     (no memory-pruning lock present now — the peer closed it)")
PY

echo
if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS — all assertions held"
else
  echo "RESULT: one or more assertions did not hold — inspect the entries above"
fi
exit "$fail"
