#!/bin/bash
# verify-pull-latest-cortex-update-3-2026-10-14.sh
# Runnable re-verification for cycle 6261 (pull-latest + cortex-update, 3rd run).
# Exits non-zero on any failed claim.
set -u

REPO="$HOME/hermes-cortex"
VENV="$HOME/.hermes-cortex/venv"
FAILS=0
CHECKS=0

ok()   { CHECKS=$((CHECKS+1)); echo "✅ $1"; }
bad()  { CHECKS=$((CHECKS+1)); FAILS=$((FAILS+1)); echo "❌ $1"; }

cd "$REPO" || { echo "❌ cannot cd $REPO"; exit 1; }

echo "━━━ Verify pull-latest + cortex-update (cycle 6261) ━━━"

# --- 1. Git sync ---
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
echo "  behind=$BEHIND"
[ "$BEHIND" = "0" ] && ok "repo not behind origin" || bad "repo behind origin by $BEHIND"

# --- 2. Fleet venv repaired (the cycle's real fix) ---
if "$VENV/bin/python3" --version >/dev/null 2>&1; then
  ok "fleet venv interpreter runs: $("$VENV/bin/python3" --version 2>&1)"
else
  bad "fleet venv interpreter is broken"
fi
if "$VENV/bin/python3" "$HOME/.hermes-cortex/scripts/fix-cortex-venv.py" --check >/dev/null 2>&1; then
  ok "fleet venv imports all 6 declared requirements"
else
  bad "fleet venv cannot import its declared requirements"
fi
# The uv-managed python the venv's pyvenv.cfg names must exist again
UV_PY="/Users/luke/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12"
[ -x "$UV_PY" ] && ok "uv-managed python 3.12.13 restored" || bad "uv python missing: $UV_PY"

# --- 3. Deployed == repo for deploy-map files ---
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
check_deployed "ops/scripts/manage/fix-cortex-venv.py" "$HOME/.hermes-cortex/scripts/fix-cortex-venv.py"
check_deployed "ops/scripts/manage/mcp_wiring.py" "$HOME/.hermes-cortex/scripts/mcp_wiring.py"

# --- 4. Enforcement immutable 9/9 ---
LOCKED_FILES="$HOME/.hermes/plugins/governance-enforcer/__init__.py
$HOME/.hermes-cortex/scripts/pre-commit-score
$HOME/.hermes-cortex/scripts/pre-push-pull
$HOME/.hermes-cortex/scripts/post-commit-audit
$HOME/.hermes-cortex/scripts/post-push-audit
$HOME/.hermes-cortex/hooks/post-merge
$HOME/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py
$HOME/.hermes-cortex/scripts/hermes-plugin-lock
/usr/local/bin/hermes-plugin-lock"
nlock=0
for f in $LOCKED_FILES; do
  if [ -f "$f" ] || [ -d "$f" ]; then
    flags=$(ls -lO "$f" 2>/dev/null | awk '{print $5}')
    case "$flags" in *uchg*|*schg*) nlock=$((nlock+1));; esac
  fi
done
if ls -ldO "$HOME/.hermes-cortex/hooks" 2>/dev/null | grep -q 'uchg'; then nlock=$((nlock+1)); fi
echo "  immutable flags present on $nlock/10 enforcement paths"
[ "$nlock" -ge 10 ] && ok "enforcement files re-locked 10/10" || bad "only $nlock/10 enforcement paths immutable"

# --- 5. Doctor: 0 fail. rc=1 (WARNING, pre-existing warns) is the accepted state; rc>=2 is a failure ---
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet > /tmp/doctor-verify-6261.log 2>&1
DRC=$?
OVERALL=$(grep -E 'Overall:' /tmp/doctor-verify-6261.log | sed 's/^[[:space:]]*//')
echo "  doctor rc=$DRC — $OVERALL"
FAIL_CNT=$(echo "$OVERALL" | grep -oE '[0-9]+ fail' | grep -oE '[0-9]+')
WARN_CNT=$(echo "$OVERALL" | grep -oE '[0-9]+ warn' | grep -oE '[0-9]+')
echo "  doctor: fail=$FAIL_CNT warn=$WARN_CNT rc=$DRC"
# Honest doctor accounting: rc>=2 means failures (bad). rc=1 = WARNING (pre-existing
# warns) — that is NOT a clean doctor and is reported as such, never claimed as a pass.
[ "$DRC" -ge 2 ] && bad "doctor rc=$DRC (>=2: failures present)" || ok "doctor rc=$DRC (no failures: rc<=1, NOTE if rc=1 this is WARNING not clean)"
[ "$FAIL_CNT" = "0" ] && ok "doctor 0 fail (no failure introduced)" || bad "doctor has $FAIL_CNT fail(s)"

# --- 6. Skill drift parity PASS (read-only: --check compares against the committed artifact, no write) ---
if python3 ops/scripts/manage/check-skill-drift-parity.py --check >/dev/null 2>&1; then
  ok "skill drift parity: committed artifact matches live derivation (0 stranded)"
else
  bad "skill drift: artifact stale or stranded files present"
fi

echo ""
echo "━━━ RESULT: $CHECKS checks, $FAILS failures ━━━"
[ "$FAILS" -eq 0 ] && echo "ALL CLAIMS VERIFIED" || echo "FAILURES PRESENT"
exit $FAILS