#!/usr/bin/env bash
# Negative tests for verify-skill-drift-parity.sh — probe THE PROBE.
#
#   bash ops/scripts/manage/test-verify-skill-drift-parity.sh ; echo "EXIT=$?"
#
# A green run of the verifier proves it accepts good state; only an INDUCED
# FAILURE proves it would notice bad state. This script builds variants of the
# verifier in a temp dir (never touching the repo), breaks exactly ONE thing per
# case, and asserts the verifier exits non-zero and names the failure.
# Exit 0 = every probe detected. Exit 1 = a probe passed silently (blind spot).
#
# Findings this closes: ADV-12698-1 — the negative-test outcomes had been
# asserted in prose with no runnable backing. Run THIS to check the claim.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
VERIFIER_SRC="$REPO/ops/scripts/manage/verify-skill-drift-parity.sh"
[ -f "$VERIFIER_SRC" ] || { echo "FAIL: verifier not found at $VERIFIER_SRC"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/parity-negtest.XXXXXX")"
pass=0; fail=0

# Build a variant: apply the per-case substitution to the ORIGINAL source
# (patterns match the relative paths as written), THEN absolutise the remaining
# tool paths so the copy works from TMP.
#   $1 = out file, $2 = sed expression (may be empty to mean "no substitution")
variant() {
  local out="$1" expr="${2:-}"
  { if [ -n "$expr" ]; then sed "$expr" "$VERIFIER_SRC"; else cat "$VERIFIER_SRC"; fi; } \
    | sed -e "s|python3 ops/scripts/|python3 $REPO/ops/scripts/|g" \
          -e "s|bash ops/scripts/|bash $REPO/ops/scripts/|g" > "$out"
  chmod +x "$out"
}

# Assert a variant fails AND its output matches the expected reason.
expect_fail() {
  local label="$1" file="$2" pat="$3" out rc
  out="$(cd "$REPO" && bash "$file" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -qE "$pat"; then
    echo "OK   $label (rc=$rc)"
    echo "       $(printf '%s' "$out" | grep -E "$pat" | head -1 | cut -c1-118)"
    pass=$((pass+1))
  else
    echo "BAD  $label -> rc=$rc, expected /$pat/"
    printf '%s\n' "$out" | head -8
    fail=$((fail+1))
  fi
}

echo "== baseline: the STOCK verifier must pass =="
if (cd "$REPO" && bash "$VERIFIER_SRC" >/dev/null 2>&1); then
  echo "OK   stock verifier passes on current state"; pass=$((pass+1))
else
  echo "BAD  stock verifier fails on current state — cannot test probes"; fail=$((fail+1))
fi

# Doctor stubs. The verifier calls `python3 <doctor>`; stubbing the path keeps
# that call shape intact.
cat > "$TMP/doctor-clean.py" <<'PYEOF'
import sys
for i in range(1, 471):
    print("  \u2705 check %d" % i)
sys.exit(1)   # the real doctor exits 1 whenever warnings exist
PYEOF
cat > "$TMP/doctor-broken.py" <<'PYEOF'
import sys
print("junk output")
sys.exit(2)
PYEOF
cat > "$TMP/doctor-nolines.py" <<'PYEOF'
import sys
print("drift?")
sys.exit(0)
PYEOF

# Baseline: doctor stubbed clean, so every downstream check is reached.
variant "$TMP/base.sh" "s|ops/scripts/manage/cortex-doctor.py|$TMP/doctor-clean.py|"
if (cd "$REPO" && bash "$TMP/base.sh" >/dev/null 2>&1); then
  echo "OK   stubbed-doctor baseline passes (probes are isolated)"; pass=$((pass+1))
else
  echo "BAD  stubbed-doctor baseline fails — probe isolation broken"; fail=$((fail+1))
  (cd "$REPO" && bash "$TMP/base.sh" 2>&1 | head -8)
fi

echo "== C1: doctor could not run =="
variant "$TMP/c1a.sh" "s|ops/scripts/manage/cortex-doctor.py|$TMP/doctor-broken.py|"
expect_fail "doctor rc=2 with junk output" "$TMP/c1a.sh" "COULD NOT VERIFY"
variant "$TMP/c1b.sh" "s|ops/scripts/manage/cortex-doctor.py|$TMP/doctor-nolines.py|"
expect_fail "doctor prints no check lines" "$TMP/c1b.sh" "COULD NOT VERIFY"

echo "== C2: reconcile could not run =="
variant "$TMP/c2.sh" "s|python3 ops/scripts/manage/reconcile-stranded-skills.py 2>&1|printf 'gibberish\\\\n'|"
expect_fail "reconcile prints no verdict line" "$TMP/c2.sh" "printed no verdict line"

echo "== C3/C4/C5: files missing =="
variant "$TMP/c3.sh" "s|^SKILLS=.*|SKILLS=\"devops/DOES-NOT-EXIST-SKILL\"|"
expect_fail "repo copy missing -> C3/C4/C5 fire" "$TMP/c3.sh" "repo copy missing"
mkdir -p "$TMP/emptyhome"
out="$(cd "$REPO" && HOME="$TMP/emptyhome" bash "$VERIFIER_SRC" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'deployed copy missing'; then
  echo "OK   deployed copy missing -> C3/C4 fire (rc=$rc)"
  echo "       $(printf '%s' "$out" | grep -m1 'deployed copy missing' | cut -c1-118)"
  pass=$((pass+1))
else
  echo "BAD  deployed copy missing not detected -> rc=$rc"
  printf '%s\n' "$out" | head -6; fail=$((fail+1))
fi

echo "== C6: scanner could not run / reported oddly =="
variant "$TMP/c6a.sh" "s|bash ops/scripts/secret-leak-detector.sh 2>&1|printf 'scanner exploded\\\\n'; exit 7|"
expect_fail "scanner non-zero WITH output" "$TMP/c6a.sh" "exited 7 - COULD NOT VERIFY"
variant "$TMP/c6b.sh" "s|bash ops/scripts/secret-leak-detector.sh 2>&1|printf 'gibberish report\\\\n'|"
expect_fail "scanner rc=0, unrecognised report" "$TMP/c6b.sh" "unrecognised report"

echo
echo "probes: ok=$pass bad=$fail"
echo "temp dir: $TMP (the OS clears it)"
[ "$fail" -eq 0 ] || exit 1
echo "ALL PROBES DETECTED"
