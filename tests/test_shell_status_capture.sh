#!/usr/bin/env bash
# Runnable proof for the two shell-status claims this range's comments make.
#
# Why a committed script instead of a sentence in a comment (adversarial finding ADV-12971-2 on
# ops/scripts/manage/agent-hermes-cortex-sync.sh): a comment that says "measured FALSE on ..." is an
# assertion about a terminal run that a later reviewer cannot see or re-run. This file is the claim
# in executable form.
#
# It pins two IDIOMS, not a copy of a shipped function — that distinction is deliberate, because a
# test of a copy proves only that the copy works. The shipped code's own behaviour is covered by the
# sources it belongs to; what is proved here is the shell semantics those lines rely on.
#
#   1. `out=$(cmd) && A || B` — B observes the status of the FAILED cmd, NOT of the `A` assignment.
#      A review claimed the assignment's 0 always won, which would make the guarded exit path dead.
#   2. The `stash_pop` status pattern — a failed pop is REPORTED and a successful one stays silent,
#      so a restore that never happened cannot look identical to one that did.
#
# Usage:  bash tests/test_shell_status_capture.sh
# Exit:   0 = both idioms behave as the comments claim; 1 = at least one claim is wrong
set -uo pipefail

FAILURES=0
check() {
    local name="$1" want="$2" got="$3"
    if [ "$want" = "$got" ]; then
        printf '  PASS  %s  [%s]\n' "$name" "$got"
    else
        printf '  FAIL  %s  [want %s, got %s]\n' "$name" "$want" "$got"
        FAILURES=$((FAILURES + 1))
    fi
}

# ── 1. the `&& A || B` status idiom ───────────────────────────────────────────────────────────
# Captured by running bash in a subshell so the caller's own $? is never involved.
got="$(bash -c 'f() { return 3; }; out=$(f 2>&1) && r=0 || r=$?; echo "$r"')"
check "a FAILED substitution reaches the || branch with ITS status (not 0)" "3" "$got"

got="$(bash -c 'g() { echo hi; return 0; }; out=$(g 2>&1) && r=0 || r=$?; echo "$r:$out"')"
check "a SUCCEEDING substitution takes the && branch and keeps stdout" "0:hi" "$got"

# Same semantics through the explicit if/else form the shipped code now uses, so the rewrite is
# shown to be equivalent rather than asserted to be.
got="$(bash -c 'f() { return 3; }; if out=$(f 2>&1); then r=0; else r=$?; fi; echo "$r"')"
check "the if/else rewrite reports the SAME status for a failure" "3" "$got"

# ── 2. the stash_pop status pattern ───────────────────────────────────────────────────────────
# `set -o pipefail` (as the shipped script sets) makes the pipeline report the LEFT command's
# failure; without it the `while` loop's 0 would win and the failure would vanish.
stash_pop_like() {
    local rc=0
    "$@" 2>&1 | while IFS= read -r line; do :; done || rc=$?
    if [ "$rc" -ne 0 ]; then echo "WARNING: pop FAILED (rc=$rc)"; fi
}

got="$( (set -o pipefail; stash_pop_like false) )"
check "a FAILED pop is REPORTED (pipefail on)" "WARNING: pop FAILED (rc=1)" "$got"

got="$( (set -o pipefail; stash_pop_like true) )"
check "a SUCCESSFUL pop stays silent" "" "$got"

# The negative control: without pipefail the failure is invisible. This is what makes the report
# above evidence about the guard rather than about the shell happening to agree.
got="$( (set +o pipefail; stash_pop_like false) )"
check "control: without pipefail the same failure would be swallowed" "" "$got"

echo
if [ "$FAILURES" -eq 0 ]; then
    echo "ALL PASS — both idioms behave as the comments claim"
    exit 0
fi
echo "FAILED — $FAILURES check(s) did not hold"
exit 1
