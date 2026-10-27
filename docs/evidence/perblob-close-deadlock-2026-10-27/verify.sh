#!/usr/bin/env bash
# Evidence generator for the per-blob close deadlock fix (cycle 13843, 2026-10-27).
#
# Re-runnable: it prints every command beside its own exit code, so a reader can re-execute the
# whole capture. By default it WRITES the committed transcript next to itself; `--stdout` prints
# instead (the mode used while developing).
#
# BASELINE IS A LITERAL, not a ref. `origin/main` is the WRONG baseline here: once the fix is
# pushed, that ref IS the fix, so the pre-change half of every comparison silently starts measuring
# the fixed code and reports that the defect never existed. The revision below is the tip the fix
# was written against, and the script ASSERTS the worktree it materialises is really that revision
# before comparing anything.
#
# Redaction: every emitted line goes through `norm`, which rewrites the home directory to `~` and
# strips ANSI colour. A transcript in a public repo must not carry a host path (and a hook's own
# coloured output lands as escape noise otherwise).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/transcript.txt"
[ "${1:-}" = "--stdout" ] && OUT=/dev/stdout

REPO="$(cd "$HERE/../../.." && pwd)"    # HERE is docs/evidence/<dir>, so the repo is THREE up
BASE_SHA="b2c2d25a76b6a18e2eb65b8f1441c23a8f164148"   # the tip this fix was written against
BASE_WT="${BASE_WT_DIR:-/tmp/hc-base-13843}"   # NOT $TMPDIR: the reproduce command below names /tmp
NEW_TESTS=(test_perblob_zero_work_is_engine_condition
           test_coverage_readers_pass_rules_rev
           test_rereview_clears_stale_blob_verdicts)
NEIGHBOURS=(test_blob_coverage_semantics test_blob_deleted_scope test_blob_judged_not_retried
            test_blob_review_concurrency test_blob_rules_rev test_close_budget_bounds
            test_per_blob_findings_recorded)

say()  { printf '%s\n' "$*"; }
norm() { sed -e "s#${HOME}#~#g" \
              -e 's/\x1b\[[0-9;]*m//g' \
              -e 's/[A-Za-z0-9._%+-]\+@[A-Za-z0-9.-]\+\.[A-Za-z]\{2,\}/<email-redacted>/g'; }
cap()  { printf '%s\n' "$*" | norm; }
# A command's status MUST be captured before any further command runs: `cmd | tail; echo rc=$?`
# prints the TAIL's status, which is how a failing run ends up recorded as rc=0.
run()  {
  local label="$1"; shift
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  printf '### %s\n' "$label" | norm
  printf '$ %s\n' "$*" | norm
  printf '%s\n' "$out" | norm
  printf 'rc=%d\n\n' "$rc"
  return 0
}

exec >"$OUT" 2>&1
say "=== per-blob close deadlock — verification transcript ==="
say "captured-by: $(basename "$0") (writes this file itself; the committed copy is the run)"
say "captured-at: HEAD=$(git -C "$REPO" rev-parse --short HEAD) (the WORKING TREE was the fix)"
say "baseline   : ${BASE_SHA:0:8} — the tip this fix was written against (a literal, never a ref:"
say "             once the fix is pushed, origin/main IS the fix and the baseline becomes a"
say "             tautology wearing a PASS)"
say "note       : 'captured-at' is the revision the tree sat on when the run happened."
say "             Writing this file changes the revision, so the committed copy is always one"
say "             commit ahead of this line — that is expected, not a drift."
say ""

say "--- 1. the fix compiles ---"
run "syntax" python3 -m py_compile "$REPO/mcp-servers/loop-gov-mcp.py"

say "--- 2. the three new pins (each must PASS on the fix) ---"
for t in "${NEW_TESTS[@]}"; do
  run "$t" python3 "$REPO/tests/$t.py"
done

say "--- 3. neighbouring suites that exercise the same seams ---"
for t in "${NEIGHBOURS[@]}"; do
  run "$t" python3 "$REPO/tests/$t.py"
done

say "--- 4. the SAME pins driven against the BASELINE SERVER (the RED half) ---"
say "Each new pin runs UNCHANGED, pointed at the baseline module through SERVER_UNDER_TEST, so the"
say "comparison is the same test against old and new code — not two different tests agreeing. The"
say "baseline then reports NAMED failures (the defect), never a crash and never a pass."
if [ -f "$BASE_WT/mcp-servers/loop-gov-mcp.py" ]; then
  got="$(git -C "$BASE_WT" rev-parse HEAD 2>/dev/null)"
  if [ "$got" = "$BASE_SHA" ]; then
    say "baseline worktree asserts: $(git -C "$BASE_WT" rev-parse --short=8 HEAD) == ${BASE_SHA:0:8}"
    say ""
    for t in "${NEW_TESTS[@]}"; do
      out="$(SERVER_UNDER_TEST="$BASE_WT/mcp-servers/loop-gov-mcp.py" \
             python3 "$REPO/tests/$t.py" 2>&1)"; rc=$?
      printf '### BASE-SERVER %s\n' "$t" | norm
      printf '$ SERVER_UNDER_TEST=<baseline module> python3 tests/%s.py\n' "$t" | norm
      printf '%s\n' "$out" | norm
      printf 'rc=%d\n\n' "$rc"
    done
  else
    say "comparison NOT RUN — $BASE_WT is at '${got:0:8}', not ${BASE_SHA:0:8}. Nothing claimed."
  fi
else
  say "comparison NOT RUN — no baseline worktree at $BASE_WT (create it with:"
  say "  git -C $REPO worktree add $BASE_WT $BASE_SHA). Nothing claimed."
fi

say "--- 5. the live symptom, quoted from the pre-change refusal ---"
say "At the baseline the refusal prints ONE path under both 'unreviewed paths' and 'judged and NOT"
say "clean', reports 'reviewed this pass : 0' as though blobs were queued work, and computes its"
say "'CLEAN in the range' count with no rules revision (so it is a structural 0). The BASE-SERVER"
say "sections above carry that output verbatim; this section adds nothing that is not printed there."

say "=== end of transcript ==="
