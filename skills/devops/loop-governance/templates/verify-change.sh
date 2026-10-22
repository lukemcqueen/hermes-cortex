#!/usr/bin/env bash
# STARTER re-runnable verifier for a governed change. Copy it, replace the sections, keep the
# shape — the shape is what answers a provenance finding. Every claim in the close note must be
# re-executed here, or it is an unverified-claim finding.
#
# Rules this encodes (do not drop them when you edit):
#   * the command's OWN rc is printed, never a piped tail's;
#   * test runners print the per-test names AND the summary;
#   * which artifact a check examined is named (repo copy vs DEPLOYED copy);
#   * the verifier states its own verdict (FAILS count) before exiting;
#   * rc 3 = COULD NOT VERIFY (a host dependency is missing) — never a pass, never a failure;
#   * it MUTATES NOTHING: operational steps (install, deploy) are separate and labelled.
#
#   bash docs/evidence/verify-<change>.sh
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2

# --- interpreter: resolve by CAPABILITY (see the shell-scripting skill) ---------------
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in "$HOME/.hermes-cortex/venv/bin/python3" python3 \
              /opt/homebrew/bin/python3 /usr/local/bin/python3 \
              "$HOME/.hermes/hermes-agent/venv/bin/python3"; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import json' >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  printf '%s\n' "COULD NOT VERIFY — no usable python3 on this host (set PYTHON=<path>)"
  exit 3
fi
printf 'interpreter: %s\n' "$PY"

FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

# A test selection: print the per-case lines, the summary AND the command's own status.
run_pytest() {
  _label="$1"; shift
  _out="$("$PY" -m pytest "$@" 2>&1)"; _rc=$?
  printf '%s\n' "$_out" | grep -E "::test_|^(FAILED|ERROR)|passed|failed|error" | sed 's/^/  /'
  say "  [${_label}] pytest rc=${_rc}"
  [ "$_rc" = 0 ] || bad "$_label"
}

# --- 1. the change's own tests, by name -----------------------------------------------
say "== 1. tests, BY NAME =="
run_pytest "1 the change's tests" tests/ -q -k "<selection>"

# --- 2. the artifact the host actually runs -------------------------------------------
say
say "== 2. the DEPLOYED copy vs the repo (name which one) =="
SRC="<repo relative path>"
DEP="$HOME/.hermes-cortex/<deployed path>"
if [ -f "$DEP" ]; then
  # Strip the deploy banner/blank lines on BOTH sides; never a fixed line count.
  if diff <(sed -E '/^#/d; /^$/d' "$SRC") <(sed -E '/^#/d; /^$/d' "$DEP") >/dev/null; then
    say "  deployed == repo modulo the deploy banner: $DEP"
  else
    bad "2 the deployed copy differs from the repo"
  fi
else
  say "  SKIP — no deployed copy on this host (a fresh checkout has none)"
fi

# --- 3. the operational step, run for real (label it) ---------------------------------
say
say "== 3. the DEPLOY, and its own log =="
DOG="$HOME/.hermes-cortex/scripts/cortex-dogfood.sh"
if [ -x "$DOG" ]; then
  _log="$(bash "$DOG" --force 2>&1)"; _rc=$?
  say "  cortex-dogfood --force rc=$_rc"
  printf '%s\n' "$_log" | grep -E "DOGFOOD PASSED|DOGFOOD FAILED|Overall:" | tail -2 | sed 's/^/  /'
  [ "$_rc" = 0 ] || bad "3 the deploy"
else
  say "  SKIP — nothing to deploy on this host"
fi

# --- 4. the adversarial gate, RAW output ----------------------------------------------
say
say "== 4. adversarial A4 (raw), with a PINNED baseline =="
AV="$HOME/.hermes-cortex/scripts/adversarial-verify.py"
if [ -f "$AV" ]; then
  _out="$(python3 "$AV" --file "$SRC" --level A4 --gate 2>&1)"
  printf '%s\n' "$_out" | grep -E "Summary:|Medium:|Low:|Info:|GATE_PASSED|GATE_FAILED" | sed 's/^/  /'
  printf '%s\n' "$_out" | grep -q "GATE_PASSED" || bad "4 A4 did not pass the gate"
  # Pin the BEFORE revision to pushed history — never a transient HEAD.
  if [ -n "${BASE:-}" ] && git show "$BASE:$SRC" > /tmp/verifier-baseline.py 2>/dev/null; then
    _bout="$(python3 "$AV" --file /tmp/verifier-baseline.py --level A4 --gate 2>&1)"
    say "  baseline $BASE: $(printf '%s\n' "$_bout" | grep -E 'Medium:|Info:|GATE_' | tr '\n' ' ')"
  fi
else
  say "  SKIP — no adversarial-verify.py here (cannot check)"
fi

say
say "FAILS: $FAILS — the verifier's own exit code follows (0 here means every claim held)"
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
