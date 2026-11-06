#!/usr/bin/env bash
# Comprehensive regression suite for the hermes-cortex -> steadfaste-fleet CLI rename
# ("hc" is now "fleet"). Two layers of coverage:
#
#   A. LAUNCHER & CLI EDGE CASES - the fleet launcher must resolve its module in both
#      installed layouts (beside the launcher / one level up), pass argv through, refuse
#      with exit 3 when no module exists anywhere, and the transition-compat `hc` shim
#      must transparently invoke `fleet`. Every fixture is local - no live bus, no host
#      state, no network.
#
#   B. MIGRATION-CONSISTENCY LINT - fail closed if any residual hermes-cortex/hc brand
#      token survives where it must not: the old package dir, the old deployed module
#      names, stale deploy-map registers, or bare-hc CLI invocations in the taught surface.
#      Historical records (docs/evidence, docs/older, dated session references) are
#      expected to keep `hc` and are excluded - the sweep must never falsify a record.
#
# Run: bash tests/test_fleet_cli_brand.sh   (no venv, no deps beyond bash + python3)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/fleet-brand.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
pass=0; fails=0
ok()  { pass=$((pass+1)); echo "  ok  $1"; }
bad() { fails=$((fails+1)); echo "  FAIL $1"; }
ck()  { # ck <label> <cmd...>  -- asserts command exit 0
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$label"; else bad "$label"; fi
}
# Files that legitimately keep the historical hc brand (dated session records, ledgers,
# an audit, one past-session evidence file) plus this suite's own grep literals. A sweep
# must never falsify a record, so these are excluded from every residual lint below.
RECORD_FILTER='2026-[0-9]{2}-|session|ledger|hc-cli-refactor-session|gbrain-reference-audit|test_fleet_cli_brand\.sh'

echo "== A. LAUNCHER & CLI EDGE CASES =="

# module that identifies itself: which fleet.py ran, and with what args
stub() { printf '#!/usr/bin/env python3\nimport sys\nprint("MODULE=" + __file__)\nprint("ARGS=" + " ".join(sys.argv[1:]))\n' > "$1"; chmod +x "$1"; }

SRC="$REPO/ops/scripts/fleet/bin/fleet"
HC_SHIM="$REPO/ops/scripts/fleet/bin/hc"
if [ ! -f "$SRC" ] || [ ! -f "$HC_SHIM" ]; then
  bad "fleet launcher + compat shim exist in repo (src=$SRC shim=$HC_SHIM)"
else
  ok "fleet launcher + compat shim exist in repo"
fi

# A1. deployed layout: module BESIDE the launcher
mkdir -p "$TMP/deploy"; cp "$SRC" "$TMP/deploy/fleet"; stub "$TMP/deploy/fleet.py"
out="$(bash "$TMP/deploy/fleet" harness verify pi 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "MODULE=.*/deploy/fleet\.py$" <<<"$out"; then ok "module beside launcher resolves (rc=0)"; else bad "module beside launcher (rc=$rc out=$out)"; fi

# A2. repo layout: launcher in bin/, module ONE LEVEL UP
mkdir -p "$TMP/repo/bin"; cp "$SRC" "$TMP/repo/bin/fleet"; stub "$TMP/repo/fleet.py"
out="$(bash "$TMP/repo/bin/fleet" y x z 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "MODULE=.*/repo/fleet\.py$" <<<"$out"; then ok "module one level up resolves"; else bad "module one level up (rc=$rc)"; fi
if grep -q "ARGS=y x z" <<<"$out"; then ok "argv passes through unchanged"; else bad "argv garbled: $out"; fi

# A3. no module anywhere -> exit 3 and names what it looked for (never runs a foreign tree's module)
mkdir -p "$TMP/none/bin" "$TMP/none/home"; cp "$SRC" "$TMP/none/bin/fleet"
out="$(HOME="$TMP/none/home" bash "$TMP/none/bin/fleet" 2>&1)"; rc=$?
if [ $rc -eq 3 ] && grep -q "cannot find fleet.py" <<<"$out"; then ok "no module anywhere exits 3 + names it"; else bad "no module anywhere (rc=$rc out=$out)"; fi

# A4. compat `hc` shim: beside fleet (deployed), invokes the fleet launcher, reports fleet brand
mkdir -p "$TMP/deployhc"; cp "$SRC" "$TMP/deployhc/fleet"; cp "$HC_SHIM" "$TMP/deployhc/hc"; stub "$TMP/deployhc/fleet.py"
out="$(bash "$TMP/deployhc/hc" probe abc 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "MODULE=.*/deployhc/fleet\.py$" <<<"$out"; then ok "compat hc (beside fleet) invokes fleet module"; else bad "compat hc beside fleet (rc=$rc out=$out)"; fi

# A5. compat `hc` shim resolves fleet one level up (repo style: shim beside fleet in bin/)
mkdir -p "$TMP/repoShim/bin"; cp "$SRC" "$TMP/repoShim/bin/fleet"; cp "$HC_SHIM" "$TMP/repoShim/bin/hc"; stub "$TMP/repoShim/fleet.py"
out="$(bash "$TMP/repoShim/bin/hc" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && grep -q "MODULE=.*/repoShim/fleet\.py$" <<<"$out"; then ok "compat hc (one level up) finds fleet module"; else bad "compat hc one-level-up (rc=$rc out=$out)"; fi

echo "== B. MIGRATION-CONSISTENCY LINT (fail closed) =="

# B1. old package dir must be gone from the active tree (repo paths)
left=$(
  grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=__pycache__ \
       --exclude-dir=evidence --exclude-dir=older --exclude-dir=sessions \
       -e 'ops/scripts/hc/' -e 'scripts/hc\.py' -e 'scripts/hc-harness\.py' "$REPO" 2>/dev/null \
    | grep -viE "$RECORD_FILTER"
)
if [ -z "$left" ]; then
  ok "no ops/scripts/hc/, scripts/hc.py, scripts/hc-harness.py in active tree"
else
  bad "residual old path refs:"; echo "$left"; fi

# B2. deploy map: every fleet register source must exist; no old hc register may remain
reg=$(grep -E 'register "ops/scripts/(hc|fleet)' "$REPO/ops/scripts/cortex-update.sh")
# flag ONLY the moved CLI package (ops/scripts/hc/{hc,harness,bin}); the gate tools
# were renamed off the hc- prefix (reflexion-check.py / plan-review-check.py).
if echo "$reg" | grep -qE 'register "ops/scripts/hc/(hc|harness|bin)'; then bad "cortex-update.sh still registers an ops/scripts/hc CLI source"; echo "$reg"; else ok "cortex-update.sh registers no old hc CLI source"; fi
while read -r line; do
  src=$(echo "$line" | sed -E 's/.*register "([^"]+)".*/\1/')
  [ -z "$src" ] && continue
  if [ -f "$REPO/$src" ]; then ok "register source exists: $src"; else bad "register source MISSING: $src"; fi
done <<<"$(echo "$reg" | grep 'ops/scripts/fleet')"

# B3. module internals are fully rebranded (no bare hc CLI, no old paths)
for f in "$REPO/ops/scripts/fleet/fleet.py" "$REPO/ops/scripts/fleet/harness.py"; do
  if grep -qE 'hc [-a-z]|ops/scripts/hc|scripts/hc-harness|hc harness' "$f"; then
    bad "stale hc token in $f:"; grep -nE 'hc [-a-z]|ops/scripts/hc|scripts/hc-harness|hc harness' "$f"
  else ok "module rebranded clean: $(basename "$f")"; fi
done

# B4. doctor resolves the NEW launcher paths, not the old ones
if grep -qE 'scripts" / "fleet"|"scripts" / "fleet"|"ops" / "scripts" / "fleet" / "bin" / "fleet"' "$REPO/ops/scripts/manage/cortex_doctor/checks.py" \
   && ! grep -qE 'CORTEX_HOME / "scripts" / "hc"|"ops" / "scripts" / "hc"' "$REPO/ops/scripts/manage/cortex_doctor/checks.py"; then
  ok "doctor harness-CLI resolver points at fleet paths"
else
  bad "doctor resolver not fully migrated:"; grep -n 'scripts" / "hc"\|scripts / "hc"\|ops / "scripts / "hc' "$REPO/ops/scripts/manage/cortex_doctor/checks.py"
fi

# B5. taught surface: no bare-CLI hc invocations in active skills/docs (records excluded)
bad_cli=$(
  grep -RInE '`?hc (send|exec|inbox|status|depth|bus|watch|kill|doctor|harness|dashboard|env|help)\b' "$REPO" \
      --include=*.md --include=*.sh --include=*.py 2>/dev/null \
      --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=__pycache__ \
      --exclude-dir=evidence --exclude-dir=older --exclude-dir=sessions \
    | grep -viE 'HC_' \
    | grep -viE "$RECORD_FILTER"
)
if [ -z "$bad_cli" ]; then
  ok "no bare-hc CLI invocations in taught (non-record) surface"
else
  bad "bare hc CLI invocations remain:"; echo "$bad_cli"
fi

echo
echo "== RESULT: $pass ok, $fails failed =="
[ $fails -eq 0 ]