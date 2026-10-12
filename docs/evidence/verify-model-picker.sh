#!/usr/bin/env bash
# Re-verify the /model inline picker in ONE run. Exits non-zero on any failed claim.
#   bash docs/evidence/verify-model-picker.sh
# Optional: BASE=<rev> adds the adversarial before/after delta (default: skipped, since
# after the feature is committed "HEAD~1" no longer means "before the feature").
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2
# The interpreter is resolved PORTABLY (2026-10-12): this verifier has to run on any agent
# host, including a macOS box with no Hermes and no cortex venv. The fleet already ships the
# resolver for exactly this (file existence says nothing about a module being importable, and
# the bare `python3` fallback is usually the one that lacks it), so use it and honour its
# contract: exit 3 is COULD NOT VERIFY, never a failed claim.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  RESOLVER="$REPO/ops/scripts/lib/python-with-module.sh"
  if [ -x "$RESOLVER" ]; then
    PY="$(bash "$RESOLVER" --print pytest 2>/dev/null)" || PY=""
  fi
fi
if [ -z "$PY" ]; then
  for cand in python3 python3.12 python3.11 python3.10 "$HOME/.hermes-cortex/venv/bin/python3" \
              /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import pytest' >/dev/null 2>&1; then
      PY="$(command -v "$cand")"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  printf '%s\n' "COULD NOT VERIFY — no interpreter on this host can import pytest." \
                "This is NOT a pass and NOT a failed claim: install pytest, or set PYTHON=<path>."
  exit 3
fi
printf 'interpreter: %s\n' "$PY"
AV="$HOME/.hermes-cortex/scripts/adversarial-verify.py"
SRC="ops/scripts/cortex_gateway/daemon.py"
DEP="$HOME/.hermes-cortex/scripts/cortex_gateway/daemon.py"
FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

say "== 0. the DEPLOY, and its own log (what is actually deployed NOW) =="
DOG="$HOME/.hermes-cortex/scripts/cortex-dogfood.sh"
if [ -x "$DOG" ]; then
  log="$(bash "$DOG" --force 2>&1)"; drc=$?
  say "  cortex-dogfood --force rc=$drc"
  printf '%s\n' "$log" | grep -E "DOGFOOD PASSED|DOGFOOD FAILED|Overall:" | tail -2 | sed 's/^/  /'
  [ "$drc" = 0 ] || bad "0 cortex-dogfood --force exited $drc"
else
  say "  SKIP — no cortex-dogfood.sh here (a fresh checkout has nothing to deploy)"
fi

say
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
if [ ! -f "$AV" ]; then
  say "  SKIP — no adversarial-verify.py on this host (a fresh checkout): cannot check"
else
  out="$(python3 "$AV" --file "$SRC" --level A4 --gate 2>&1)"
  printf '%s\n' "$out" | grep -E "📊 Summary|Medium:|Low:|Info:|GATE_PASSED|GATE_FAILED" | sed 's/^/  /'
  printf '%s\n' "$out" | grep -q "GATE_PASSED" || bad "3 A4 did not pass the gate"
fi

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
say "== 5. the wider gateway selection (the regression sweep) =="
"$PY" -m pytest tests/ -q -k "gateway or harness or startup" 2>&1 | tail -1 | sed 's/^/  /'
[ "${PIPESTATUS[0]}" = 0 ] || bad "5 the gateway selection"

say
say "== 6. the enabler every OTHER agent host runs (portable, stdlib only) =="
"$PY" -m pytest tests/test_gateway_model_list_helper.py -q 2>&1 | tail -1 | sed 's/^/  /'
[ "${PIPESTATUS[0]}" = 0 ] || bad "6 the enabler's tests"
ENABLER=ops/scripts/manage/gateway-model-list.py
tmp="$(mktemp -d)"
printf '{"backends":[{"name":"pi","model_args":["--model","{model}"]}],"routing":{"default":"pi"}}\n' > "$tmp/gw.json"
printf 'openrouter/openai/gpt-5\nopenrouter/x-ai/grok-4\n' > "$tmp/pi.txt"
"$PY" "$ENABLER" --config "$tmp/gw.json" --from-file "$tmp/pi.txt" --write >/dev/null 2>&1 \
  && say "  write rc=0 on a config with other keys" || bad "6 the enabler could not write"
"$PY" "$ENABLER" --config "$tmp/gw.json" --check 2>&1 | sed 's/^/  /'
[ "${PIPESTATUS[0]}" = 0 ] || bad "6 --check on what it just wrote"
"$PY" - "$tmp/gw.json" <<'PY' | sed 's/^/  /'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["backends"][0]["model_args"] == ["--model", "{model}"], "a models: write disturbed a backend"
assert d["models"]["list"] == ["openrouter/openai/gpt-5", "openrouter/x-ai/grok-4"], d["models"]
print("other keys intact; models:", d["models"])
PY
[ "${PIPESTATUS[0]}" = 0 ] || bad "6 the write disturbed other config keys"
rm -rf "$tmp"

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
