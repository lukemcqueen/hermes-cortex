#!/usr/bin/env bash
# Re-verify the kustos-class failure end to end: the wrapper names what is missing, and the
# deploy's venv check fires on an ABSENT venv. Prints each test case BY NAME so the artifact
# carries the evidence, not a claim about it. Exit non-zero on any failed claim.
#
#   bash docs/evidence/verify-loop-gov-diagnosable.sh
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in "$HOME/.hermes-cortex/venv/bin/python3" python3; do
    command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import json' >/dev/null 2>&1 && { PY="$cand"; break; }
  done
fi
[ -n "$PY" ] || { echo "COULD NOT VERIFY — no usable python3 here"; exit 3; }
FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

say "== the wrapper's guard, case by case =="
out="$("$PY" tests/test_loop_gov_wrapper_guard.py 2>&1)"; rc=$?
printf '%s\n' "$out" | sed 's/^/  /'
say "  [wrapper guard] rc=$rc"
[ "$rc" = 0 ] || bad "the wrapper guard tests"

say
say "== the deploy's venv check with the venv ABSENT / partial / healthy =="
out="$("$PY" tests/test_fleet_venv_check_block.py 2>&1)"; rc=$?
printf '%s\n' "$out" | sed 's/^/  /'
say "  [fleet venv check block] rc=$rc"
[ "$rc" = 0 ] || bad "the fleet venv check block tests"

say
say "== the CLASS: no launcher may bare-exec the fleet venv =="
out="$("$PY" tests/test_fleet_venv_launchers.py 2>&1)"; rc=$?
printf '%s\n' "$out" | sed 's/^/  /'
say "  [fleet launcher sweep] rc=$rc"
[ "$rc" = 0 ] || bad "the fleet launcher sweep"

say
say "== the DEPLOYED wrapper, on a HOME with no venv (what kustos saw) =="
WRAP="$HOME/.hermes-cortex/scripts/loop-gov-mcp.sh"
if [ -f "$WRAP" ]; then
  tmp_home="$(mktemp -d)"
  msg="$(HOME="$tmp_home" bash "$WRAP" 2>&1)"; mrc=$?
  printf '%s\n' "$msg" | head -3 | sed 's/^/  /'
  say "  rc=$mrc (78 = EX_CONFIG)"
  [ "$mrc" = 78 ] || bad "the deployed wrapper must exit 78 on a missing venv (got $mrc)"
  printf '%s\n' "$msg" | grep -q "NO INTERPRETER" || bad "it must name which piece is missing"
  printf '%s\n' "$msg" | grep -q "No such file or directory" && bad "it still emits bash's generic error"
else
  say "  SKIP — no deployed wrapper on this host"
fi

say
say "== 7. the docs and controls a bounded review window cannot see =="
# The review's material is truncated, so "the docs say so" is unverifiable from its window.
# Print the decisive lines HERE so they ride in the artifact instead of in a claim.
T=docs/troubleshooting.md
if [ -f "$T" ]; then
  say "  -- docs/troubleshooting.md, the lines that matter --"
  grep -n "executable" "$T" | head -1 | sed 's/^/  /'
  grep -n "Three causes, three fixes\|three fixes" "$T" | head -1 | sed 's/^/  /'
  grep -n "Both present" "$T" | head -1 | sed 's/^/  /'
  grep -n "require-fleet-venv.sh" "$T" | head -1 | sed 's/^/  /'
  grep -n "| 1.9.0 |" "$T" | head -1 | sed 's/^/  changelog: /'
  for want in "python3 -m venv ~/.hermes-cortex/venv" "78 (EX_CONFIG)"; do
    grep -q "$want" "$T" && say "  ✓ present: $want" || bad "7 troubleshooting is missing: $want"
  done
else
  bad "7 docs/troubleshooting.md is missing"
fi
say "  -- the DEPLOY really carries the self-heal (not the doc's word for it) --"
for want in "Created the fleet venv" "no usable bin/python3"; do
  grep -q "$want" ops/scripts/cortex-update.sh \
    && say "  ✓ cortex-update.sh: $want" || bad "7 cortex-update.sh is missing: $want"
done
say "  -- the sweep's controls, BY NAME (not a tautology) --"
grep -n "^def test_" tests/test_fleet_venv_launchers.py | sed 's/^/  /'
grep -q "def test_the_sweep_would_catch_a_bare_exec" tests/test_fleet_venv_launchers.py \
  || bad "7 the sweep has no control proving the detector fires"
say "  -- the guard-missing branch, its actual message --"
_lone="$(mktemp -d)"
cp ops/scripts/manage/loop-gov-mcp.sh "$_lone/loop-gov-mcp.sh"
_lmsg="$(HOME="$(mktemp -d)" bash "$_lone/loop-gov-mcp.sh" 2>&1)"; _lrc=$?
printf '%s\n' "$_lmsg" | head -2 | sed 's/^/  /'
say "  rc=$_lrc"
printf '%s\n' "$_lmsg" | grep -q "NOT DEPLOYED at" || bad "7 the guard branch must name the file"
printf '%s\n' "$_lmsg" | grep -q "require-fleet-venv.sh" || bad "7 and name the guard path"

say
say "FAILS: $FAILS — the verifier's own exit code follows (0 here means every claim held)"
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
