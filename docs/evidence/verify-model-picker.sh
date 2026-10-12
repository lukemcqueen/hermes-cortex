#!/usr/bin/env bash
# Re-verify the /model inline picker in ONE run. Exits non-zero on any failed claim.
#   bash docs/evidence/verify-model-picker.sh
# Optional: BASE=<rev> adds the adversarial before/after delta (default: skipped, since
# after the feature is committed "HEAD~1" no longer means "before the feature").
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2
PY="${PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python3}"
AV="$HOME/.hermes-cortex/scripts/adversarial-verify.py"
SRC="ops/scripts/cortex_gateway/daemon.py"
DEP="$HOME/.hermes-cortex/scripts/cortex_gateway/daemon.py"
FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

say "== 1. the picker's tests, BY NAME =="
"$PY" -m pytest tests/test_gateway_slash_parity.py -v -k "menu or model" --tb=line -q 2>&1 \
  | grep -E "::test_|passed" | sed 's/^/  /'
[ "${PIPESTATUS[0]}" = 0 ] || bad "1 the model/menu tests"

say
say "== 1b. the WHOLE file (so a subset claim cannot outrun its evidence) =="
"$PY" -m pytest tests/test_gateway_slash_parity.py -q 2>&1 | tail -1 | sed 's/^/  /'
[ "${PIPESTATUS[0]}" = 0 ] || bad "1b the whole parity file"

say
say "== 2. the DEPLOYED copy this host runs =="
if [ ! -f "$DEP" ]; then
  say "  SKIP — no deployed gateway here (a fresh checkout): nothing to compare"
else
  # The deploy INSERTS a SOURCE banner whose shape differs per file type, so the
  # comparison strips leading comment AND blank lines on both sides (never a fixed line
  # count — that mis-reports a script carrying the banner after its shebang). The claim
  # is therefore "identical modulo the deploy banner and blank lines", not byte-identity.
  if diff <(sed -E '/^#/d; /^$/d' "$SRC") <(sed -E '/^#/d; /^$/d' "$DEP") >/dev/null; then
    say "  deployed == repo modulo the deploy banner / blank lines: $DEP"
  else
    bad "2 the deployed gateway differs from the repo — the running copy is not this code"
  fi
  say "  picker symbols in the DEPLOYED file: $(grep -c "_handle_model_callback\|_model_menu_view\|PICKER_PREFIX" "$DEP")"
  say "  menu config reachable in the DEPLOYED file: $(grep -c "menu_page_size\|menu_list" "$DEP")"
fi

say
say "== 3. adversarial A4 (raw output), and the gate criterion =="
out="$(python3 "$AV" --file "$SRC" --level A4 --gate 2>&1)"
printf '%s\n' "$out" | grep -E "📊 Summary|Medium:|Low:|Info:|GATE_PASSED|GATE_FAILED" | sed 's/^/  /'
printf '%s\n' "$out" | grep -q "GATE_PASSED" || bad "3 A4 did not pass the gate"

if [ -n "${BASE:-4efcb1a3}" ]; then
  # PINNED by default to the commit the picker branched from (immutable: it is pushed
  # history), so the before/after delta is reproducible instead of resting on a
  # transient HEAD. Override with BASE=<rev>, or BASE= to skip.
  say
  say "== 4. against the pinned pre-change baseline ${BASE:-4efcb1a3} =="
  git show "${BASE:-4efcb1a3}:$SRC" > /tmp/verify-picker-baseline.py 2>/dev/null \
    || { bad "4 cannot read ${BASE:-4efcb1a3}:$SRC"; }
  if [ -f /tmp/verify-picker-baseline.py ]; then
    for f in /tmp/verify-picker-baseline.py "$SRC"; do
      bout="$(python3 "$AV" --file "$f" --level A4 --gate 2>&1)"
      say "  $(basename "$f"): $(printf '%s\n' "$bout" \
        | grep -E 'Summary:|Medium:|Low:|Info:|GATE_PASSED|GATE_FAILED' | tr '\n' ' ' | tr -s ' ')"
    done
  fi
fi

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
