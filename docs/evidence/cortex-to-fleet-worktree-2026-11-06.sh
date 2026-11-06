#!/usr/bin/env bash
# Evidence capture — working-tree / residue state for the cortex->fleet plan (§4.7, §4.8).
# READ-ONLY. Run from the repo root.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "REPO=$PWD"
echo "HEAD=$(git rev-parse HEAD)"
echo "origin/main=$(git rev-parse origin/main)"
echo "captured=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "=== 1. working tree (git status --short) ==="
git status --short
echo
echo "=== 2. staged deletions: names WITHOUT and WITH --no-renames ==="
echo "--- git diff --cached --name-only (rename-collapsed) ---"
git diff --cached --name-only
echo "--- git diff --cached --name-only --no-renames ---"
git diff --cached --name-only --no-renames
echo "--- staged diffstat ---"
git diff --cached --stat | tail -3
echo
echo "=== 3. do the hc- originals still exist in HEAD? ==="
for p in ops/scripts/hc-plan-review-check.py ops/scripts/hc-reflexion-check.py plugins/hc-lean-index/__init__.py plugins/hc-lean-index/plugin.yaml; do
  if git ls-tree -r HEAD --name-only -- "$p" | grep -q .; then echo "  IN HEAD      $p"; else echo "  NOT in HEAD  $p"; fi
done
echo
echo "=== 4. residue directories (prior 2026-11-04 attempt) ==="
for d in core/fleet_bus ops/scripts/manage/fleet_doctor ops/scripts/fleet; do
  if [ -e "$d" ]; then
    echo "--- $d ---"
    ls -la "$d" | sed 's/^/    /'
    echo "    tracked files under it: $(git ls-files "$d" | wc -l)"
    echo "    untracked file count:   $(git ls-files --others --exclude-standard "$d" | wc -l)"
  else
    echo "--- $d --- ABSENT"
  fi
done
echo
echo "=== 5. was fleet-update.sh ever a committed source? ==="
echo "git log --all -- ops/scripts/fleet-update.sh  ->  $(git log --all --oneline -- ops/scripts/fleet-update.sh | wc -l) commit(s)"
echo "git log --all -- ops/scripts/cortex-update.sh ->  $(git log --all --oneline -- ops/scripts/cortex-update.sh | wc -l) commit(s)"
echo
echo "=== 6. provenance of the staged deletions ==="
echo "current branch: $(git rev-parse --abbrev-ref HEAD)"
echo "staged deletions are uncommitted; last commit on this branch:"
git log -1 --format='  %h %ad %an %s' --date=iso
echo "orphaned PENDING cycles in the local governance DB (may block push):"
python3 - <<'PY'
import sqlite3, pathlib
db = pathlib.Path.home()/".steadfaste-fleet"/"data"/"loop-governance.db"
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = list(con.execute("SELECT id, task_id, session_id FROM loop_cycles WHERE decision='PENDING'"))
    con.close()
    for r in rows:
        print("  ", r)
    if not rows:
        print("   (none)")
except Exception as e:
    print("   ERR", e)
PY
