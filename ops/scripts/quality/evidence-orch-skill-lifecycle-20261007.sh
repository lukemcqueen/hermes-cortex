#!/usr/bin/env bash
# orch-skill-lifecycle run evidence — 2026-10-07 (cycle #10787)
# Re-runnable: reproduces every claim made in the cycle note at the named revision.
set -uo pipefail
REPO="${HOME}/hermes-cortex"
STAGE="${HOME}/.hermes-cortex/state/learning-reports"
REV="6b3c2aaa"
FAIL=0

hr() { printf '\n===== %s =====\n' "$1"; }
chk() { # name, expected, actual
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s = %s\n' "$1" "$3"
  else printf 'FAIL  %s: expected %s got %s\n' "$1" "$2" "$3"; FAIL=1; fi
}

hr "revision"
cd "$REPO" || exit 2
git log --oneline -1 "$REV"
echo "HEAD=$(git rev-parse HEAD)"
echo "origin/main=$(git rev-parse origin/main)"

hr "P1a: staged learning reports in last 24h (deduped by body Generated ts + agent)"
python3 - "$STAGE" <<'PY'
import os,glob,re,json,sys
from datetime import datetime,timedelta,timezone
d=sys.argv[1]
cut=datetime.now(timezone.utc)-timedelta(hours=24)
seen={}
for f in glob.glob(os.path.join(d,"*.md")):
    try: body=open(f,encoding="utf-8",errors="replace").read()
    except OSError: continue
    m=re.search(r'Generated:\s*([0-9T:\.\+\-Z]+)',body)
    if not m: continue
    try: ts=datetime.fromisoformat(m.group(1).replace("Z","+00:00"))
    except ValueError: continue
    if ts<cut: continue
    am=re.search(r'Learning Report — (\S+)',body)
    agent=am.group(1) if am else "?"
    seen[(ts.isoformat(),agent)]=f
print(f"unique reports (24h) = {len(seen)}")
for k in sorted(seen): print("  ",k[1],k[0])
PY

hr "P1b: git commits in last 24h"
echo "count = $(git log --since='24 hours ago' --oneline | wc -l)"

hr "P1c: doctor summary"
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet 2>&1 | grep -E "Skill drift|Overall"

hr "P3a: the 2 drift-synced skills — deployed == repo (md5) + fences even"
for s in deploy-load-verification governance-closeout; do
  a=$(md5sum "$REPO/skills/devops/$s/SKILL.md" | cut -d' ' -f1)
  b=$(md5sum "$HOME/.hermes/skills/devops/$s/SKILL.md" | cut -d' ' -f1)
  fa=$(grep -c '^```' "$REPO/skills/devops/$s/SKILL.md")
  chk "$s md5" "$a" "$b"
  chk "$s fences even" "$((fa%2))" "0"
done

hr "P3b: upstreamed fleet skill — md5 local vs moses source + version + no stub"
SS="software-development/large-mechanical-refactor"
chk "SKILL.md md5 (repo==moses)" \
  "$(ssh -o ConnectTimeout=10 mosesaaron "md5sum ~/.hermes/skills/$SS/SKILL.md" 2>/dev/null | cut -d' ' -f1)" \
  "$(md5sum "$REPO/skills/$SS/SKILL.md" | cut -d' ' -f1)"
chk "ref md5 (repo==moses)" \
  "$(ssh -o ConnectTimeout=10 mosesaaron "md5sum ~/.hermes/skills/$SS/references/async-conversion-rust.md" 2>/dev/null | cut -d' ' -f1)" \
  "$(md5sum "$REPO/skills/$SS/references/async-conversion-rust.md" | cut -d' ' -f1)"
echo "version field: $(grep -m1 '^version:' "$REPO/skills/$SS/SKILL.md")"
echo "stub markers:  $(grep -c 'SKILL_PRUNED\|content unavailable' "$REPO/skills/$SS/SKILL.md")"
echo "deployed copy: $(ls "$HOME/.hermes/skills/$SS/SKILL.md" 2>/dev/null || echo MISSING)"

hr "FINAL"
if [[ "$FAIL" == "0" ]]; then echo "RESULT: all assertions PASS"; else echo "RESULT: FAILURES present"; fi
exit "$FAIL"
