#!/usr/bin/env bash
# Capture the before/after for the test-pollution fixes (issues #213 and #214): the same test
# files run at a PINNED pre-change revision and at the working tip, with the two side effects
# measured — the tracked evidence tree, and the LIVE shared governance state dir.
#
# Read-only with respect to the product. It does clean up the ONE artefact its own baseline probe
# creates (a lock file in the live state dir), because leaving it would re-break a different test
# on the next run — that is the probe's own side effect, not a repair of what it measures.
#
# Re-run: bash docs/evidence/test-pollution-fix-2026-10-21.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
TMP="${TMPDIR:-/tmp}/pollution-fix.$$"
mkdir -p "$TMP" || exit 2
STATE="$HOME/.hermes-cortex/state"
OUT="docs/evidence/test-pollution-fix-2026-10-21.txt"

# PINNED BASELINE: the commit this change sits on, whose test files still write the live tree.
# A `git merge-base origin/main HEAD` baseline would resolve to the tip before the commit and to
# the fix itself after a push, so it would silently stop discriminating.
BASE_PIN="3b03c92cf7d31143d7c69aa35e10a3e5c1d7c86c"

exec >"$OUT" 2>&1

say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME}#~#g"; }
locks() { ls "$STATE"/.governance-*.json 2>/dev/null | xargs -n1 basename 2>/dev/null | sort; }

say "generated-by: docs/evidence/test-pollution-fix-2026-10-21.sh   (this file IS that script's stdout)"
say "host-date:    $(date -Is)"
say "captured-at:  $(git rev-parse HEAD)"
say "              ^ the revision the working tree sat on WHEN THIS WAS CAPTURED; the change under"
say "                test was UNCOMMITTED at that moment."
say "committed-in: the commit that ADDS this file — always one commit ahead of captured-at. A"
say "              transcript cannot name its own commit: writing this file changes the revision."
say "baseline:     $BASE_PIN   (PINNED — the last pre-change revision)"

rule "1. THE BASELINE — the two offending files run at the pinned revision"
say "The baseline is a git worktree at $BASE_PIN. Its test files still write their output into"
say "the tracked evidence tree and a real lock into the LIVE shared state dir."
say ""
BASE_WT="$TMP/base-wt"
git worktree add -q "$BASE_WT" "$BASE_PIN" 2>"$TMP/wt.err"
if [ $? -ne 0 ]; then
  say "comparison NOT RUN, nothing claimed: could not create a worktree at $BASE_PIN"
  sed -e "s#${HOME}#~#g" "$TMP/wt.err" | head -3
else
  resolved="$(git -C "$BASE_WT" rev-parse HEAD)"
  say "worktree resolves to: $(git -C "$BASE_WT" rev-parse --short=8 HEAD)"
  if [ "$resolved" != "$BASE_PIN" ]; then
    say "comparison NOT RUN, nothing claimed: checkout is $resolved, not $BASE_PIN"
  else
    say "ASSERTED: the checkout is exactly $BASE_PIN"
    # Prove the extracted copy really is the PRE-change revision: the isolation marker this
    # change introduced must be ABSENT from it.
    if grep -q "OUT_EVID" "$BASE_WT/tests/test_write_cycle_evidence.py"; then
      say "comparison NOT RUN, nothing claimed: the baseline copy already carries OUT_EVID"
    else
      say "ASSERTED: 'OUT_EVID' is absent from the baseline copy of test_write_cycle_evidence.py"
      say "          (so the baseline really is the pre-change revision)"
      say ""
      locks_before="$(locks)"
      say "live state dir before: $(printf '%s' "$locks_before" | tr '\n' ' ')"
      bash "$BASE_WT/tests/run-tests.sh" "$BASE_WT/tests/test_write_test_results.py" \
        "$BASE_WT/tests/test_write_closure_note.py" "$BASE_WT/tests/test_write_cycle_evidence.py" \
        "$BASE_WT/tests/test_runtime/test_adversarial_review_gate.py" -q --color=no \
        > "$TMP/base-run.txt" 2>&1
      brc=$?
      say "  baseline run rc=$brc   $(grep -aE '[0-9]+ (passed|failed)' "$TMP/base-run.txt" | tail -1)"
      say ""
      say "--- SIDE EFFECT 1: the TRACKED evidence tree, in the baseline worktree"
      say "    command: git -C <worktree> status --porcelain docs/evidence/"
      dirty="$(git -C "$BASE_WT" status --porcelain --untracked-files=no docs/evidence/ || true)"
      if [ -n "$dirty" ]; then
        printf '%s\n' "$dirty" | sed -e "s#^#    #" | norm
        say "    -> $(printf '%s\n' "$dirty" | grep -c .) tracked file(s) left DIRTY by running tests"
      else
        say "    -> (none) — unexpected: the baseline should dirty these files"
      fi
      say ""
      say "--- SIDE EFFECT 2: the LIVE shared governance state dir"
      locks_after="$(locks)"
      new="$(comm -13 <(printf '%s\n' "$locks_before") <(printf '%s\n' "$locks_after") | grep -v '^$' || true)"
      say "live state dir after : $(printf '%s' "$locks_after" | tr '\n' ' ')"
      if [ -n "$new" ]; then
        say "    -> CREATED BY THE TEST: $(printf '%s' "$new" | tr '\n' ' ')"
        say "    -> this is the probe's own side effect; removing it so the next test run is not"
        say "       poisoned by it (issue #214). The fix under test removes the CAUSE."
        for f in $new; do rm -f "$STATE/$f"; done
        say "    -> after cleanup       : $(locks | tr '\n' ' ')"
      else
        say "    -> (none) — unexpected: the baseline should create a lock file"
      fi
    fi
  fi
  git worktree remove --force "$BASE_WT" >/dev/null 2>&1 || rm -rf "$BASE_WT"
fi

rule "2. THE FIX — the same files run at the working tree"
locks_before="$(locks)"
dirty_before="$(git status --porcelain --untracked-files=no docs/evidence/ || true)"
say "tracked evidence tree before: $(printf '%s\n' "$dirty_before" | grep -c . ) modified tracked path(s)"
say "live state dir before      : $(printf '%s' "$locks_before" | tr '\n' ' ')"
say ""
bash tests/run-tests.sh tests/test_write_test_results.py tests/test_write_closure_note.py \
  tests/test_write_cycle_evidence.py tests/test_gateway_parity_evidence.py \
  tests/test_runtime/test_adversarial_review_gate.py -q --color=no > "$TMP/tip-run.txt" 2>&1
trc=$?
say "  working-tree run rc=$trc   $(grep -aE '[0-9]+ (passed|failed)' "$TMP/tip-run.txt" | tail -1)"
say "  (the 5 failures in test_runtime/test_adversarial_review_gate.py are the PRE-EXISTING set"
say "   already attributed at this range's base — see"
say "   docs/evidence/sweep-json-rows-and-engine-error-2026-10-21.txt section 9, REPRODUCED.)"
say ""
dirty_after="$(git status --porcelain --untracked-files=no docs/evidence/ || true)"
locks_after="$(locks)"
say "tracked evidence tree after : $(printf '%s\n' "$dirty_after" | grep -c . ) modified tracked path(s)"
say "live state dir after       : $(printf '%s' "$locks_after" | tr '\n' ' ')"
# Compare the SETS: pre-existing dirt that the run neither caused nor cleared is not a finding,
# and a count alone would call this script's own new files pollution.
if [ "$dirty_before" = "$dirty_after" ] && [ "$locks_before" = "$locks_after" ]; then
  say "  -> CLEAN BOTH WAYS: running these suites no longer writes the tracked evidence tree or"
  say "     the live shared state dir."
else
  say "  -> STILL POLLUTING — see the lists above"
fi

rule "end of transcript"
rm -rf "$TMP"
