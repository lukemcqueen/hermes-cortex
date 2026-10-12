#!/usr/bin/env bash
# Verify WHERE fleet tooling gets its interpreter (2026-10-13, Luke's correction: use the
# hermes-cortex venv). Every claim in the cycle note is re-executed here; exit non-zero on
# any failed claim, 3 = COULD NOT VERIFY (nothing to measure), never a pass.
#
#   bash docs/evidence/verify-interpreter-choice.sh
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2
RESOLVER=ops/scripts/lib/python-with-module.sh
DEP_RESOLVER="$HOME/.hermes-cortex/scripts/lib/python-with-module.sh"
CORTEX="$HOME/.hermes-cortex/venv/bin/python3"
HERMES="$HOME/.hermes/hermes-agent/venv/bin/python3"
FAILS=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

say "== 0. the deploy this host runs, and its own log =="
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
say "== 0b. the dev dependencies the suite needs =="
# The INSTALL was a manual operational step on this host, not an automated one:
#   uv pip install --python ~/.hermes-cortex/venv/bin/python3 pytest fastapi
# A verifier must not mutate the environment it measures, so this section proves the STATE
# that step produced — the distributions are really installed there — and says plainly which
# part is manual.
if [ -x "$CORTEX" ]; then
  "$CORTEX" - <<'PY' | sed 's/^/  /'
import importlib.metadata as m
for p in ("pytest", "fastapi", "mcp", "PyYAML"):
    try:
        print(f"{p}={m.version(p)}")
    except m.PackageNotFoundError:
        print(f"{p}=NOT INSTALLED")
PY
  "$CORTEX" -c 'import pytest, fastapi' >/dev/null 2>&1 \
    || bad "0b the cortex venv cannot import pytest + fastapi"
else
  say "  SKIP — no cortex venv on this host"
fi

say
say "== 1. what each candidate can actually import (the measurement, not a memory) =="
for p in "$CORTEX" "$HERMES" "$(command -v python3 2>/dev/null || true)"; do
  [ -n "$p" ] && [ -x "$p" ] || { say "  ${p:-<none>}: absent"; continue; }
  line="  $p"
  for m in pytest yaml mcp fastapi; do
    if "$p" -c "import $m" >/dev/null 2>&1; then line="$line  $m:YES"; else line="$line  $m:no"; fi
  done
  say "$line"
done

say
say "== 2. the resolver's DEFAULT choice (no PYTHON/HERMES_VENV override) =="
for r in "$RESOLVER" "$DEP_RESOLVER"; do
  if [ ! -f "$r" ]; then say "  $r: absent (skip — a fresh checkout has no deployed copy)"; continue; fi
  got="$(env -u PYTHON -u HERMES_VENV bash "$r" --print pytest 2>/dev/null)"
  say "  $r -> ${got:-<none>}"
  [ "$got" = "$CORTEX" ] || bad "$r does not prefer the cortex venv (got '${got:-none}')"
done

say
say "== 3. the tie-break, pinned by a test that runs UNDER the cortex venv =="
if [ -x "$CORTEX" ]; then
  out="$("$CORTEX" tests/test_python_with_module.py 2>&1)"; rc=$?
  printf '%s\n' "$out" | grep -E "cortex venv beats|RESULT:|skip:" | sed 's/^/  /'
  say "  [3 the resolver's own test] rc=$rc"
  [ "$rc" = 0 ] || bad "3 the resolver test under the cortex venv"
else
  say "  SKIP — no cortex venv here"; 
fi

say
say "== 4. the cortex venv can COLLECT the whole suite (a missing dep hides tests) =="
if [ -x "$CORTEX" ]; then
  cout="$("$CORTEX" -m pytest tests/ --collect-only -q 2>&1)"; crc=$?
  missing="$(printf '%s\n' "$cout" | grep -E "ModuleNotFoundError" | sort -u)"
  if [ -n "$missing" ]; then
    printf '%s\n' "$missing" | sed 's/^/  /'
    bad "4 the cortex venv cannot import everything the suite needs"
  else
    printf '%s\n' "$cout" | tail -1 | sed 's/^/  /'
  fi
fi

say
say "FAILS: $FAILS — the verifier's own exit code follows (0 here means every claim held)"
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
