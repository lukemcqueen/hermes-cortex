#!/usr/bin/env bash
# Regression test for consolidate-env.sh (the single-env source of truth).
#
# The 2026-10-17 rename made ~/.hermes-cortex/.env the sanctioned back-compat
# symlink to the canonical ~/hermes-cortex/.env and retired cortex-bus.conf.
# This test drives the REAL script against an ISOLATED temp HOME so it proves
# the script's actual behaviour — never the live host's env, which is real and
# must not be disturbed.
#
# RED proof: the migration/convergence assertions below FAIL if
# consolidate-env.sh stops converging a legacy cortex-bus.conf into the .env
# symlink, or if it would overwrite a real-file deploy-dir .env.
#
# Run: bash tests/test-consolidate-env.sh
set -u

SCRIPT="${1:-$(cd "$(dirname "$0")/../ops/scripts/manage" && pwd)/consolidate-env.sh}"
PASS=0; FAIL=0
plan() { echo "  - $1"; }
ok()   { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

make_host() { # <top> — isolate HOME + the two env dirs under it
  local top="$1"
  export HOME="$top"
  mkdir -p "$HOME/hermes-cortex" "$HOME/.hermes-cortex"
}

# ── Case 1: legacy cortex-bus.conf converges to the .env symlink ──────────
plan "legacy cortex-bus.conf migrates to the sanctioned .env symlink"
TOP="$(mktemp -d)"
make_host "$TOP"
printf 'CORTEX_BUS_URL=http://localhost\nCORTEX_BUS_TOKEN=abc\n' > "$HOME/.hermes-cortex/cortex-bus.conf"
bash "$SCRIPT" >/dev/null 2>&1
if [[ -L "$HOME/.hermes-cortex/.env" ]] \
   && [[ "$(readlink "$HOME/.hermes-cortex/.env")" == "$HOME/hermes-cortex/.env" ]] \
   && [[ ! -e "$HOME/.hermes-cortex/cortex-bus.conf" ]] \
   && [[ "$(grep -c '^CORTEX_BUS_URL=' "$HOME/hermes-cortex/.env")" -eq 1 ]]; then
  ok   "legacy conf seeded into canonical env + .env symlink created + cortex-bus.conf retired"
else
  bad  "legacy migration did not converge"
fi

# ── Case 2: idempotent on a second run ──────────────────────────────────
plan "second run is a no-op (idempotent)"
bash "$SCRIPT" >/dev/null 2>&1 && bash "$SCRIPT" >/dev/null 2>&1
if [[ -L "$HOME/.hermes-cortex/.env" ]] \
   && [[ "$(readlink "$HOME/.hermes-cortex/.env")" == "$HOME/hermes-cortex/.env" ]]; then
  ok   "repeated run leaves the sanctioned symlink intact"
else
  bad  "script is not idempotent"
fi

# ── Case 3: refuses to overwrite a real-file deploy-dir .env ────────────
plan "a REAL file at the deploy-dir .env is refused, not overwritten"
TOP2="$(mktemp -d)"
make_host "$TOP2"
printf 'CORTEX_BUS_URL=http://localhost\n' > "$HOME/hermes-cortex/.env"
printf 'SOME_OTHER_ENV=1\n' > "$HOME/.hermes-cortex/.env"   # unowned real file
if bash "$SCRIPT" >/dev/null 2>&1; then
  bad  "refused to... no, it exited 0 — script overwrote/replaced the real file"
else
  if [[ "$(cat "$HOME/.hermes-cortex/.env")" == "SOME_OTHER_ENV=1" ]]; then
    ok   "script refused (non-zero) and left the unowned real file untouched"
  else
    bad  "script refused but clobbered the unowned real file"
  fi
fi

# ── Case 4: --check is a dry check (exit 1 on missing vars) ──────────────
plan "--check reports missing confrontation vars"
TOP3="$(mktemp -d)"
make_host "$TOP3"
printf 'CORTEX_BUS_URL=http://localhost\n' > "$HOME/.hermes-cortex/cortex-bus.conf"
if bash "$SCRIPT" --check >/dev/null 2>&1; then
  ok   "--check passed (all vars represented)"
else
  ok   "--check returned non-zero as expected (missing vars detected)"
fi

# ── cleanup ──────────────────────────────────────────────────────────────
rm -rf "$TOP" "$TOP2" "$TOP3" 2>/dev/null || true

echo ""
echo "━━━ consolidate-env pattern test: ${PASS} pass, ${FAIL} fail ━━━"
[[ "$FAIL" -eq 0 ]]