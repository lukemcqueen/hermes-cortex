#!/usr/bin/env bash
# test-reflexion-gate-repoint.sh — the re-pointed reflexion gate's contract.
#
# The gate no longer queries Hermes's conversation DB; it delegates to
# hc-reflexion-check.py, which answers from HC's OWN session/memory store.
#
# This test is HERMETIC: it extracts the real block out of ops/scripts/pre-commit-score
# and runs it against a STUB verifier in a temp dir, so the result never depends on
# ambient lock/journal/DB state. (The first version of the CLI refusal test passed
# only because an unrelated stale lock happened to exist — a probe that tests the
# machine instead of the code. Not repeating that.)
#
# Covered:
#   AC1 verifier says LOADED       → gate passes (rc 0)
#   AC2 verifier says NOT-LOADED   → gate REFUSES (rc 1)
#   AC3 verifier says store down   → gate REFUSES (rc 1, fail-closed)
#   AC4 verifier missing           → gate REFUSES (rc 1) with an actionable message
#   AC5 non-HC repo                → gate SKIPS (rc 0)
#   AC6 sanctioned pipeline commit → gate SKIPS (rc 0)
#   AC7 the real verifier refuses  → hermetically, a session with no evidence
#
# Run: bash tests/test-reflexion-gate-repoint.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_DIR}/ops/scripts/pre-commit-score"
CHECKER="${REPO_DIR}/ops/scripts/hc-reflexion-check.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

P=0; F=0
pass() { P=$((P + 1)); echo "  ✅ $1"; }
fail() { F=$((F + 1)); echo "  ❌ $1${2:+ — $2}"; }

# ── Extract the REAL block, anchored on markers (never line numbers) ──
BLOCK="$WORK/block.sh"
awk '/── Reflexion gate/{p=1} p{print} p && /^fi$/{exit}' "$SRC" > "$BLOCK"
if ! grep -q "hc-reflexion-check" "$BLOCK"; then
  echo "❌ could not extract the re-pointed reflexion block from $SRC" >&2
  exit 1
fi

# run_case <stub_exit|none> <is_cortex_repo> <sanctioned> → prints rc
run_case() {
  local stub="$1" cortex="$2" sanctioned="$3"
  local root="$WORK/root"
  rm -rf "$root"; mkdir -p "$root/ops/scripts"
  if [[ "$stub" != "none" ]]; then
    # The gate invokes the verifier with python3 (it is a python script), so the
    # stub must be python too — a bash stub would fail to parse and every case
    # would "pass" for the wrong reason.
    printf 'import sys\nsys.exit(%s)\n' "$stub" > "$root/ops/scripts/hc-reflexion-check.py"
  fi
  {
    echo 'set -uo pipefail'
    echo "SANCTIONED_PIPELINE=$sanctioned"
    echo "IS_CORTEX_REPO=$cortex"
    echo "REPO_ROOT=$root"
    echo "HOME=$WORK/home"     # never find a real deployed verifier by accident
    cat "$BLOCK"
  } > "$WORK/case.sh"
  mkdir -p "$WORK/home"
  bash "$WORK/case.sh" > "$WORK/out.txt" 2>&1
  echo $?
}

echo ""
echo "═══ AC1: verifier says LOADED → gate passes ═══"
[[ "$(run_case 0 1 0)" == "0" ]] && pass "loaded session passes the gate" || fail "gate blocked a loaded session"

echo ""
echo "═══ AC2: verifier says NOT-LOADED → gate refuses ═══"
RC=$(run_case 1 1 0)
if [[ "$RC" == "1" ]] && grep -q "Reflexion check not completed" "$WORK/out.txt"; then
  pass "not-loaded session is refused with an explanation"
else
  fail "not-loaded session was not refused (rc=$RC)" "$(head -3 "$WORK/out.txt")"
fi

echo ""
echo "═══ AC3: store unreachable → gate REFUSES (fail-closed) ═══"
RC=$(run_case 3 1 0)
[[ "$RC" == "1" ]] && pass "unverifiable outcome fails closed rather than passing" || fail "store-unreachable passed the gate (rc=$RC)"

echo ""
echo "═══ AC4: verifier missing → gate refuses, actionably ═══"
RC=$(run_case none 1 0)
if [[ "$RC" == "1" ]] && grep -q "verifier missing" "$WORK/out.txt"; then
  pass "missing verifier refuses and names the fix"
else
  fail "missing verifier did not refuse actionably (rc=$RC)" "$(head -3 "$WORK/out.txt")"
fi

echo ""
echo "═══ AC5/AC6: skip paths preserved (non-HC repo, sanctioned pipeline) ═══"
[[ "$(run_case 1 0 0)" == "0" ]] && pass "non-HC repo skips the gate" || fail "non-HC repo was gated"
[[ "$(run_case 1 1 1)" == "0" ]] && pass "sanctioned pipeline commit skips the gate" || fail "sanctioned pipeline commit was gated"

echo ""
echo "═══ AC7: the real verifier ═══"
if [[ ! -f "$CHECKER" ]]; then
  fail "hc-reflexion-check.py missing"
else
  out=$(python3 "$CHECKER" --session "definitely-no-such-session-$$" 2>&1); rc=$?
  [[ "$rc" == "1" ]] && pass "refuses a session with no recorded evidence" || fail "did not refuse an unknown session (rc=$rc)"

  out=$(python3 "$CHECKER" --skill "" 2>&1); rc=$?
  [[ "$rc" == "2" ]] && pass "empty --skill is a usage error" || fail "empty --skill gave rc=$rc, expected 2"

  # Exit 3 must be reachable at all — a checker that can only say yes/no cannot
  # fail closed when the store is down.
  grep -q "EXIT_STORE_UNREACHABLE = 3" "$CHECKER" && \
    pass "verifier defines a distinct store-unreachable code" || \
    fail "verifier has no distinct store-unreachable code"
fi

echo ""
echo "═══ AC8: STORE-ONLY — an enforcer-journal-only session is REFUSED ═══"
# The transitional bridge (accept HC's enforcer journal while the store had no row)
# was deleted once the enforcer writer was proven live: a real skill_view landed a
# tool_events row with no manual recording, and the verifier answered from the
# store. If the bridge ever returns, this fails — a session HC's journal credits
# but the store does not know must NOT pass, or the store stops being authoritative
# and the Hermes-shaped coupling is back.
JOURNAL_SID="probe-journal-only-$$"
mkdir -p "$HOME/.hermes-cortex/state/skills-credit"
printf '{"session":"%s","skills":["reflexion-check"]}\n' "$JOURNAL_SID" \
  > "$HOME/.hermes-cortex/state/skills-credit/$JOURNAL_SID.json"
out=$(python3 "$CHECKER" --session "$JOURNAL_SID" 2>&1); rc=$?
rm -f "$HOME/.hermes-cortex/state/skills-credit/$JOURNAL_SID.json"
if [[ "$rc" == "1" ]]; then
  pass "journal-only session refused — the store is authoritative, bridge gone"
else
  fail "journal-only session PASSED (rc=$rc) — the bridge is back" "$out"
fi
if grep -q "journal_skill_loaded" "$CHECKER"; then
  fail "the bridge function is still present in the verifier"
else
  pass "no bridge code remains in the verifier"
fi

echo ""
echo "═══ AC9: STORE UNREACHABLE → rc 3, fail-closed, actionable ═══"
# Exercised WITHOUT any production seam. The verifier resolves its store module
# relative to its OWN location (`<parent>/../ops/services/mycortex-mem/store.py`)
# and then $HOME, so a copy of it in a temp tree finds only what this test puts
# there. Deliberately no env-var override in production code: an override lets a
# caller point the gate at a stub that answers "loaded" for anything, which is a
# bigger hole than the one being closed.
NOSEAM="$WORK/noseam"
mkdir -p "$NOSEAM/ops/scripts" "$WORK/home"
cp "$CHECKER" "$NOSEAM/ops/scripts/hc-reflexion-check.py"

# (a) no store module at all
out=$(HOME="$WORK/home" python3 "$NOSEAM/ops/scripts/hc-reflexion-check.py" --session any 2>&1); rc=$?
if [[ "$rc" == "3" ]] && echo "$out" | grep -q "cortex-update.sh"; then
  pass "store module missing → rc 3, names the fix"
else
  fail "missing store module gave rc=$rc (expected 3)" "$out"
fi

# (b) store present but unreachable — the branch a fleet outage hits
mkdir -p "$NOSEAM/ops/services/mycortex-mem"
printf 'class Store:\n    def __init__(self, *a, **k): pass\n    def available(self): return False\n' \
  > "$NOSEAM/ops/services/mycortex-mem/store.py"
out=$(HOME="$WORK/home" python3 "$NOSEAM/ops/scripts/hc-reflexion-check.py" --session any 2>&1); rc=$?
if [[ "$rc" == "3" ]] && echo "$out" | grep -q "mycortex-postgres"; then
  pass "store unreachable → rc 3 with the actionable fix named"
else
  fail "store unreachable gave rc=$rc (expected 3, fail-closed)" "$out"
fi

echo ""
echo "═══ AC10: store raises mid-query → rc 3, no stack dump leaked ═══"
printf 'class _S:\n    def loaded_skill(self, *a, **k):\n        raise RuntimeError("internal detail that must not be dumped raw")\n\nclass Store:\n    def __init__(self, *a, **k):\n        self.sessions = _S()\n    def available(self):\n        return True\n' \
  > "$NOSEAM/ops/services/mycortex-mem/store.py"
out=$(HOME="$WORK/home" python3 "$NOSEAM/ops/scripts/hc-reflexion-check.py" --session any 2>&1); rc=$?
[[ "$rc" == "3" ]] && \
  pass "an exception inside the store still refuses (rc 3), never crashes or passes" || \
  fail "store exception gave rc=$rc (expected 3)" "$out"
if echo "$out" | grep -q "Traceback"; then
  fail "a stack trace reached the gate output (leaks internals to the commit log)"
else
  pass "no stack trace in the gate output"
fi
[[ "$(echo "$out" | wc -l)" -le 1 ]] && \
  pass "gate output stays a single line (no raw dump)" || \
  fail "gate output was multi-line"
grep -q "HC_REFLEXION_STORE_MODULE\|getenv" "$CHECKER" && \
  fail "the verifier still reads a store-path override from the environment" || \
  pass "no run-time store-path override exists in the verifier"

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
if [ "$F" -gt 0 ]; then
  echo "  ❌ SOME TESTS FAILED"
  exit 1
fi
echo "  ✅ ALL TESTS PASSED"
