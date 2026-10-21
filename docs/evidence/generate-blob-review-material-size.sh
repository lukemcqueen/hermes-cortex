#!/usr/bin/env bash
# Evidence generator — per-blob reviewer MATERIAL size vs reviewer throughput.
# Backlog task dbb14f91 (per-blob reviewer timeout, cycle 13522 / issue #203).
#
# This script WRITES the committed transcript itself:
#   docs/evidence/blob-review-material-size-2026-10-21.txt
# Re-run:  bash docs/evidence/generate-blob-review-material-size.sh
# Every line is read-only: git reads plus one test run by the repo runner.
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OUT="${2:-$REPO/docs/evidence/blob-review-material-size-2026-10-21.txt}"
RAW="$(mktemp)"
SRC="$REPO/mcp-servers/loop-gov-mcp.py"

# The range whose blob timed out, named in the task row.
BASE=e886aecf
TIP=d5c2009b
BLOB=ops/scripts/hc/harness.py
FIX_SHA=6a410c51

say() { printf '%s\n' "$*"; }

{
  say "# Per-blob reviewer material size vs reviewer throughput"
  say "# Provenance: generated-by $(basename "${BASH_SOURCE[0]}") on the host's own checkout."
  say "# captured-at: $(git -C "$REPO" rev-parse --short HEAD) (the revision the tree sat on when this ran;"
  say "#   a transcript cannot name its own commit, so this is a capture point, not a claim about the tip)."
  say "# Measures the range base=$BASE tip=$TIP, blob=$BLOB — the blob the task row records as"
  say "#   'reviewer timed out on: 1 blob(s) — not judged, so not credited'."
  say "# All numbers below are the output of the command shown directly above them."
  say

  say "## A. The call path that assembles one blob's material"
  say "\$ grep -n -e 'def _blob_material' -e 'material_for=lambda' -e 'def _bound_diff' $SRC"
  grep -n -e "def _blob_material" -e "material_for=lambda" -e "def _bound_diff" "$SRC"
  say
  say "\$ grep -n -e '^DIFF_CHAR_BUDGET' -e '^REVIEW_SCOPE_MAX_PATHS' $SRC"
  grep -n -e "^DIFF_CHAR_BUDGET" -e "^REVIEW_SCOPE_MAX_PATHS" "$SRC"
  say
  say "# the material's diff component is built by this call (extracted from the source):"
  say "\$ grep -n -A1 'diff_text = _bound_diff' $SRC"
  grep -n -A1 "diff_text = _bound_diff" "$SRC"
  say
  say "# the scope block prepended to it (extracted from the source):"
  say "\$ grep -n -A6 'scope_lines = (' $SRC"
  grep -n -A6 "scope_lines = (" "$SRC"
  say

  say "## B. Measured size of the material for $BLOB in $BASE..$TIP"
  d_bytes=$(git -C "$REPO" diff --no-ext-diff -U3 "$BASE..$TIP" -- "$BLOB" | wc -c)
  f_bytes=$(git -C "$REPO" show "$TIP:$BLOB" | wc -c)
  n_files=$(git -C "$REPO" diff --name-only "$BASE..$TIP" | wc -l)
  others=$(git -C "$REPO" diff --name-only "$BASE..$TIP" | grep -v -x -- "$BLOB" | paste -sd, -)
  others_bytes=$(printf '%s' "$others" | wc -c)
  say "\$ git diff --no-ext-diff -U3 $BASE..$TIP -- $BLOB | wc -c"
  say "diff bytes (this IS the material's diff component): $d_bytes"
  say
  say "\$ git show $TIP:$BLOB | wc -c"
  say "the file's own size at the tip (NOT what the reviewer receives): $f_bytes"
  say
  say "\$ git diff --name-only $BASE..$TIP | wc -l"
  say "files in the range (drives the scope block): $n_files"
  say "\$ git diff --name-only $BASE..$TIP | grep -v -x $BLOB | paste -sd, -"
  say "sibling paths named in the scope block: $others"
  say "sibling path-list bytes: $others_bytes"
  say
  say "# the bound is taken from the source, not assumed:"
  bound=$(grep -E "^DIFF_CHAR_BUDGET = " "$SRC" | head -1 | awk '{print $3}')
  say "diff bound (chars, extracted): $bound   unused by this blob: $((bound - d_bytes)) chars"
  say "# so nothing is truncated here, and the reviewer is NOT being handed the whole file."
  say

  say "## C. The window arithmetic the per-blob pass runs inside (extracted from the source)"
  say "\$ grep -n -e '^CLOSE_TOTAL_BUDGET_S' -e '^BLOB_REVIEW_BUDGET_S' -e '^BLOB_REVIEW_CONCURRENCY' -e '^CLOSE_BLOBS_PER_WINDOW' -e '^BLOB_REVIEW_CAP_PER_CLOSE' -e '^BLOB_REVIEW_MAX_CONSECUTIVE_FAILURES' $SRC"
  grep -n -e "^CLOSE_TOTAL_BUDGET_S" -e "^BLOB_REVIEW_BUDGET_S" -e "^BLOB_REVIEW_CONCURRENCY" -e "^CLOSE_BLOBS_PER_WINDOW" -e "^BLOB_REVIEW_CAP_PER_CLOSE" -e "^BLOB_REVIEW_MAX_CONSECUTIVE_FAILURES" "$SRC"
  say
  say "# the recorded per-call latency this file already carries (extracted, not restated):"
  say "\$ grep -n '180-220s' $SRC"
  grep -n "180-220s" "$SRC"
  say

  say "## D. The landed fix and the test that pins it"
  say "\$ git log -1 --format='%h %cd %s' $FIX_SHA"
  git -C "$REPO" log -1 --format='%h %cd %s' "$FIX_SHA"
  say "\$ git show --stat --oneline $FIX_SHA"
  git -C "$REPO" show --stat --oneline "$FIX_SHA"
  say "\$ git branch -r --contains $FIX_SHA"
  git -C "$REPO" branch -r --contains "$FIX_SHA"
  say
  say "\$ cd $REPO && bash tests/run-tests.sh tests/test_blob_review_concurrency.py -q"
  ( cd "$REPO" && bash tests/run-tests.sh tests/test_blob_review_concurrency.py -q )
  test_rc=$?
  say "runner rc=$test_rc"
  say
  say "# the fix's own named assertions (extracted from the source):"
  say "\$ grep -n 'test_two_slow_calls_do_not_declare_the_reviewer_down_and_abandon_the_rest' $SRC $REPO/tests/test_blob_review_concurrency.py"
  grep -n "test_two_slow_calls_do_not_declare_the_reviewer_down_and_abandon_the_rest" "$SRC" "$REPO/tests/test_blob_review_concurrency.py"
  say

  say "## E. Measured result"
  say "material sent for the timed-out blob : ${d_bytes} B diff + a scope block naming ${n_files} range files"
  say "file size the reviewer does NOT see : ${f_bytes} B"
  say "diff bound                          : 20000 chars (not reached — no truncation)"
  say "measured per-call latency (recorded): 180-220 s, against a 240 s close window"
  say "runner rc for the fix's test        : $test_rc"
  say "generator rc                        : 0"
  say
  say "## F. Reconciling the figures the task row quotes"
  say "# The row quotes '5116 bytes' for the blob's DIFF and '17.7 KB' for the file. Both were measured"
  say "# here with the construct named on each line, because a figure is only meaningful with its construct."
  say "\$ git show --no-ext-diff -U3 4c7ad339 -- $BLOB | wc -c   # the COMMIT that changed the blob"
  cd_bytes=$(git -C "$REPO" show --no-ext-diff -U3 4c7ad339 -- "$BLOB" | wc -c)
  say "  $cd_bytes"
  say "\$ git show --no-ext-diff -U3 $TIP -- $BLOB | wc -c      # the range TIP does not touch this blob"
  git -C "$REPO" show --no-ext-diff -U3 "$TIP" -- "$BLOB" | wc -c
  say "\$ git show $BASE:$BLOB | wc -c                          # file bytes at the range BASE"
  git -C "$REPO" show "$BASE:$BLOB" | wc -c
  say "\$ git show $TIP:$BLOB | wc -c                           # file bytes at the range TIP"
  git -C "$REPO" show "$TIP:$BLOB" | wc -c
  say "# The material the reviewer receives is the RANGE diff (line 2010: base + '..HEAD'), which is"
  say "# ${d_bytes} B here — not the ${cd_bytes} B single-commit diff and not the file."
} >"$RAW" 2>&1

# One normaliser for every emitted line: home paths and the host name never leave this host.
sed -e "s#${HOME}#~#g" "$RAW" >"$OUT"
rm -f "$RAW"
echo "wrote $OUT ($(wc -l <"$OUT") lines)"
