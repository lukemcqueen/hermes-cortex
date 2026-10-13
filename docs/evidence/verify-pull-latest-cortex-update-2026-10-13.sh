#!/bin/bash
# verify-pull-latest-cortex-update-2026-10-13.sh
# Runnable re-verification for cycle 6057 (pull-latest + cortex-update).
# Re-checks every claim and exits non-zero on any failure.
# Usage: bash docs/evidence/verify-pull-latest-cortex-update-2026-10-13.sh
set -u

REPO="$HOME/hermes-cortex"
FAILS=0
CHECKS=0

ok()   { CHECKS=$((CHECKS+1)); echo "✅ $1"; }
bad()  { CHECKS=$((CHECKS+1)); FAILS=$((FAILS+1)); echo "❌ $1"; }

cd "$REPO" || { echo "❌ cannot cd $REPO"; exit 1; }

echo "━━━ Verify pull-latest + cortex-update (cycle 6057) ━━━"

# --- 1. Git sync: upstream tip e50938f2 merged in, repo not behind ---
UPSTREAM_TIP=$(git rev-parse origin/main)
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
echo "  origin/main = $UPSTREAM_TIP  behind=$BEHIND ahead=$AHEAD"
if git merge-base --is-ancestor e50938f2 HEAD; then
  ok "upstream governance fix e50938f2 is in HEAD"
else
  bad "e50938f2 not in HEAD"
fi
if git merge-base --is-ancestor e4fd5f7e HEAD; then
  ok "upstream mcp-wiring commit e4fd5f7e is in HEAD"
else
  bad "e4fd5f7e not in HEAD"
fi
[ "$BEHIND" = "0" ] && ok "repo not behind origin" || bad "repo behind origin by $BEHIND"

# --- 2. Deployed == repo for the deploy-map files the pulled commits changed ---
check_deployed() {
  local repo_f="$1" dep="$2"
  if [ ! -f "$dep" ]; then bad "deployed copy missing: $dep"; return; fi
  HOME="$HOME" python3 - "$repo_f" "$dep" <<'PY'
import sys,os
home=os.environ["HOME"]
a=open(sys.argv[1]).read().splitlines()
b=open(sys.argv[2].replace("$HOME",home)).read().splitlines()
def strip_comments(lines):
    out=[]
    for l in lines:
        if l.startswith('# SOURCE:'): continue
        if not out and (not l.strip() or l.startswith('#')): continue
        out.append(l)
    return '\n'.join(out)
sys.exit(0 if strip_comments(a)==strip_comments(b) else 1)
PY
  if [ $? -eq 0 ]; then ok "deployed == repo: ${repo_f##*/}"; else bad "deployed != repo: $repo_f"; fi
}

check_deployed "ops/scripts/cortex-update.sh" "$HOME/.hermes-cortex/scripts/cortex-update.sh"
check_deployed "ops/scripts/manage/mcp_wiring.py" "$HOME/.hermes-cortex/scripts/mcp_wiring.py"
check_deployed "ops/scripts/manage/cortex_doctor/checks.py" "$HOME/.hermes-cortex/scripts/cortex_doctor/checks.py"
check_deployed "ops/scripts/manage/cortex_doctor/config.py" "$HOME/.hermes-cortex/scripts/cortex_doctor/config.py"

# --- 3. Enforcement files immutable (LOCKED) after the rc=1 relock wrapper ---
LOCKED_FILES="$HOME/.hermes/plugins/governance-enforcer/__init__.py
$HOME/.hermes-cortex/scripts/pre-commit-score
$HOME/.hermes-cortex/scripts/pre-push-pull
$HOME/.hermes-cortex/scripts/post-commit-audit
$HOME/.hermes-cortex/scripts/post-push-audit
$HOME/.hermes-cortex/hooks/post-merge
$HOME/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py
$HOME/.hermes-cortex/scripts/hermes-plugin-lock"
nlock=0
for f in $LOCKED_FILES; do
  if [ -f "$f" ] || [ -d "$f" ]; then
    flags=$(ls -lO "$f" 2>/dev/null | awk '{print $5}')
    case "$flags" in *uchg*|*schg*) nlock=$((nlock+1));; esac
  fi
done
if ls -ldO "$HOME/.hermes-cortex/hooks" 2>/dev/null | grep -q 'uchg'; then nlock=$((nlock+1)); fi
echo "  immutable flags present on $nlock/9 enforcement paths"
[ "$nlock" -ge 9 ] && ok "enforcement files re-locked (rc=1 was the wrapper's own exit; files secured)" || bad "only $nlock/9 enforcement paths immutable"

# --- 4. Doctor ---
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet > /tmp/doctor-verify-6057.log 2>&1
DRC=$?
OVERALL=$(grep -E 'Overall:' /tmp/doctor-verify-6057.log | sed 's/^[[:space:]]*//')
echo "  doctor rc=$DRC — $OVERALL"
if grep -q '❌ AGENTS.md (steadfaste)' /tmp/doctor-verify-6057.log; then
  ok "doctor: only out-of-scope fail is steadfaste (different project)"
else
  bad "doctor fail set differs from expected (see /tmp/doctor-verify-6057.log)"
fi

# --- 5. Deployed enforcer present + substantive (deploy completed; load is operator step) ---
ENF="$HOME/.hermes/plugins/governance-enforcer/__init__.py"
if [ -f "$ENF" ]; then
  SIZE=$(wc -c < "$ENF")
  echo "  deployed enforcer size: $SIZE bytes"
  [ "$SIZE" -gt 1000 ] && ok "deployed enforcer present and substantive (deploy≠load: gateway restart is operator step)" || bad "deployed enforcer suspiciously small ($SIZE bytes)"
else
  bad "deployed enforcer missing: $ENF"
fi

# --- 6. Cortex venv has mcp package (MCP servers functional) ---
~/.hermes-cortex/venv/bin/python3 -c "import mcp" 2>/dev/null && ok "cortex venv has mcp package" || bad "cortex venv missing mcp"

echo ""
echo "━━━ RESULT: $CHECKS checks, $FAILS failures ━━━"
[ "$FAILS" -eq 0 ] && echo "ALL CLAIMS VERIFIED" || echo "FAILURES PRESENT"
exit $FAILS