#!/usr/bin/env bash
# Reproducible PROOF that the failing loop-governance regression tests are PRE-EXISTING.
#
# Why this script is committed rather than described (adversarial finding ADV-12971-1 on
# docs/evidence/close-budget-bound-2026-10-18.txt): that file records
# `python3 tests/run_loop_gov_regression.py` as rc=1 with five failing files. A note that SAYS
# "these predate my change" is an unverifiable claim — a later reviewer has nothing to re-run.
#
# This script is the re-runnable form of that claim. It checks out the PARENT revision into a
# throwaway git worktree and runs the same files at BOTH revisions, then reports per file whether
# the two outcomes AGREE. Agreement on a FAILURE means that failure is not introduced by the change
# under test; a DIFFERENCE means this script exits non-zero so the regression is not waved away.
#
# THREE OUTCOMES, NEVER TWO (2026-10-18). The first version compared bare exit CODES, so a file
# that could not execute at all — no interpreter, a timeout, a crash before any test ran — returned
# the same code on both sides and was reported "SAME (pre-existing)". That is a claim made from two
# unmeasured runs. Every run is now CLASSIFIED as PASS / FAIL / NOT RUN by reading its output, and:
#   * NOT RUN is never a pass and never a failure of the code under test;
#   * two runs that both executed nothing are COULD NOT VERIFY (exit 3), not agreement;
#   * a file that PASSES at the CURRENT revision is reported as LIST DRIFT (exit 1) — it is no
#     longer part of any "failing set", so keeping it here would make this artifact's scope
#     silently disagree with its claim.
#
# Usage:  bash tests/verify_preexisting_failures.sh [parent-rev]     (default: HEAD~1)
#         PREEXISTING_TESTS="a.py b.py" bash tests/verify_preexisting_failures.sh   (override list)
#         bash tests/verify_preexisting_failures.sh --classify-only <rc> <output-file>
# Exit:   0 = every listed file FAILS identically at both revisions (claim proven)
#         1 = a file differs between revisions, OR the list has drifted (a listed file now passes)
#         2 = the harness itself could not run (bad revision, no git, worktree refused)
#         3 = COULD NOT VERIFY — at least one run executed nothing, so no claim can be made
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="${1:-HEAD~1}"
PER_TEST_TIMEOUT="${PER_TEST_TIMEOUT:-200}"

# Exactly the files the runner reports as failing. Scope of the artifact must equal scope of
# the claim, so this list is the failing set and nothing else — and the drift check below FAILS
# if a listed file stops failing, which is what keeps the two in step without anyone remembering.
# (On 2026-10-18 all five listed files were fixed, and this script said so instead of continuing to
# compare them: the list is now empty of claims, not silently stale.)
DEFAULT_TESTS=(
  "tests/run_non_hermes_lock_release_repro.py"
  "tests/test_loop_gov_stale_purge.py"
  "tests/test_reviewer_backends.py"
  "tests/test_refused_close_visible.py"
  "tests/test_python_with_module.py"
)
if [ -n "${PREEXISTING_TESTS:-}" ]; then
  # shellcheck disable=SC2206
  TESTS=( ${PREEXISTING_TESTS} )
else
  TESTS=( "${DEFAULT_TESTS[@]}" )
fi

# THREE OUTCOMES, named apart. Read the OUTPUT as well as the exit code: a non-zero code with no
# failure named anywhere is the harness being unable to establish anything, and calling that
# "failed" is how a broken probe gets reported as a defect in the code under test.
classify() {  # classify <rc> <output-file> -> PASS | FAIL | NOTRUN
  local rc="$1" out="$2"
  case "$rc" in
    124|126|127) printf 'NOTRUN'; return ;;   # timed out, or could not invoke at all
  esac
  if [ -f "$out" ] && grep -qE 'RESULT: FAIL|^FAILED:|^[0-9]+ FAILED:|FAIL  test_|Traceback \(most recent call last\)' "$out"; then
    printf 'FAIL'; return
  fi
  if [ "$rc" = "0" ]; then
    # An empty log verified nothing either way — a run that produced no output at all cannot be
    # read as a pass (measured: a run whose whole log was the kernel release string, `7.0.0-38-generic`).
    [ -s "$out" ] || { printf 'NOTRUN'; return; }
    printf 'PASS'; return
  fi
  printf 'NOTRUN'
}

# Self-test seam: the classifier is the whole safety property here, so it is drivable on its own.
if [ "${1:-}" = "--classify-only" ]; then
  classify "${2:?rc required}" "${3:?output file required}"; printf '\n'; exit 0
fi

tmp="$(mktemp -d)" || exit 2
outdir="$(mktemp -d)" || exit 2
cleanup() {
  git -C "$REPO" worktree remove --force "$tmp" >/dev/null 2>&1 || rm -rf "$tmp"
  rm -rf "$outdir"
}
trap cleanup EXIT

# macOS ships GNU coreutils as `gtimeout` (brew coreutils); Linux ships `timeout`. Never assume the
# binary exists — name the gap instead of failing with a cryptic 127.
#
# SCOPE OF THE CLAIM, stated narrowly on purpose. What is PROVEN is that the fallback branch works:
# it was exercised on Linux with a PATH that contains NO `timeout` at all, only a `gtimeout` shim —
#
#   d=/tmp/gtimeout-shim; rm -rf "$d"; mkdir -p "$d"
#   for t in bash sh git python3 mktemp rm dirname basename sed grep head; do ln -s "$(command -v $t)" "$d/$t"; done
#   printf '#!/bin/sh\nexec /usr/bin/timeout "$@"\n' > "$d/gtimeout"; chmod +x "$d/gtimeout"
#   env PATH="$d" bash tests/verify_preexisting_failures.sh <rev>      # rc=0, all rows SAME
#
# (`env PATH=<dir> ... command -v timeout` must print nothing — otherwise the shim is not the branch
# being taken, which is how a first attempt at this "proof" silently tested the GNU path instead.)
# A run on ACTUAL macOS is NOT claimed: none has been performed. If one is, record its output here.
TIMEOUT_CMD=""
for _c in timeout gtimeout; do
  if command -v "$_c" >/dev/null 2>&1; then TIMEOUT_CMD="$_c"; break; fi
done
if [ -z "$TIMEOUT_CMD" ]; then
  echo "verify_preexisting_failures: neither 'timeout' nor 'gtimeout' on PATH" >&2
  echo "  (macOS: brew install coreutils — it provides gtimeout)" >&2
  exit 2
fi

# The interpreter is checked for the same reason the timeout binary is. Both are invoked through a
# `timeout N python3 <file>` pipeline, so a missing binary would surface as a 126/127 exit code that
# would otherwise be read as THE TEST'S OWN RESULT — and the comparison that is the entire point of
# the file would be comparing two shell errors. Verified up front, the exit codes below can only
# come from the tests themselves. (A 126/127 mid-loop is now classified NOT RUN rather than FAILED,
# so the claim cannot be manufactured from a broken probe even if one slips through.)
command -v python3 >/dev/null 2>&1 || {
  echo "verify_preexisting_failures: python3 not found on PATH" >&2; exit 2; }

git -C "$REPO" rev-parse --verify --quiet "$PARENT" >/dev/null || {
  echo "cannot resolve revision '$PARENT' in $REPO" >&2; exit 2; }
PARENT_SHA="$(git -C "$REPO" rev-parse --short "$PARENT")"
HEAD_SHA="$(git -C "$REPO" rev-parse --short HEAD)"

git -C "$REPO" worktree add -q "$tmp" "$PARENT" || {
  echo "could not create a worktree at $PARENT_SHA" >&2; exit 2; }

echo "parent revision : $PARENT_SHA   (worktree $tmp)"
echo "current         : $HEAD_SHA    (working tree $REPO)"
echo
printf '%-44s %-16s %-16s %s\n' "test file" "parent" "current" "verdict"

differ=0; drift=0; unverified=0
for t in "${TESTS[@]}"; do
  b="$(basename "$t")"
  curout="$outdir/cur.$b.log"; parout="$outdir/par.$b.log"
  ( cd "$REPO" && "$TIMEOUT_CMD" "$PER_TEST_TIMEOUT" python3 "$t" >"$curout" 2>&1 ); cur=$?
  ( cd "$tmp"  && "$TIMEOUT_CMD" "$PER_TEST_TIMEOUT" python3 "$t" >"$parout" 2>&1 ); par=$?
  curk="$(classify "$cur" "$curout")"
  park="$(classify "$par" "$parout")"
  if [ "$curk" = "NOTRUN" ] || [ "$park" = "NOTRUN" ]; then
    verdict="COULD NOT VERIFY — a side executed nothing"
    unverified=1
  elif [ "$curk" = "PASS" ]; then
    verdict="*** NO LONGER FAILING — list has drifted; regenerate ***"
    drift=1
  elif [ "$park" = "FAIL" ]; then
    verdict="SAME (FAIL pre-existing)"
  else
    verdict="*** DIFFERENT — not pre-existing ***"
    differ=1
  fi
  printf '%-44s %-16s %-16s %s\n' "$t" "rc=$par/$park" "rc=$cur/$curk" "$verdict"
done

echo
if [ "$unverified" = 1 ]; then
  echo "RESULT: COULD NOT VERIFY — a listed file executed nothing on one of the two revisions."
  echo "        Two unmeasured runs are not agreement. Fix the probe/interpreter, then re-run."
  echo "        (Recorded 2026-10-18: comparing bare exit codes reported exactly this as SAME.)"
  exit 3
fi
if [ "$drift" = 1 ]; then
  echo "RESULT: LIST DRIFT — at least one listed file now PASSES at $HEAD_SHA, so it is no longer"
  echo "        part of any failing set. Remove it (or regenerate the list) and re-run: an artifact"
  echo "        whose scope no longer matches its claim reads as authoritative and is not."
  exit 1
fi
if [ "$differ" = 1 ]; then
  echo "RESULT: at least one file differs between $PARENT_SHA and $HEAD_SHA — the change is"
  echo "        implicated. Treat the differing file as a regression from this range."
  exit 1
fi
echo "RESULT: every listed failure reproduces identically on $PARENT_SHA before the change,"
echo "        so none of them is a regression introduced by $HEAD_SHA."
exit 0
