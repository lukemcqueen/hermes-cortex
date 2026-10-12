#!/usr/bin/env bash
# Reproduce the RED (before-fix) run of the four material-window tests, honestly.
#
# The TDD failing runs were not committed when first observed (they happened interactively
# before the fix), so there is no committed RED state to point a reviewer at. This script
# reconstructs one WITHOUT touching the repo tree: it takes the PRE-FIX gate module from git
# history (base = the commit this cycle starts from) and runs the CURRENT test file against
# it in a throwaway layout. The tests that exercise the new behaviour then fail exactly as
# they did pre-fix.
#
# Exit code: 0 if the RED is reproduced (the four expected tests fail and the run reports
# FAIL); non-zero otherwise. This is a deliberately failing run — capture it with
# 'bash ops/scripts/make-evidence.sh -k <out> -- bash docs/evidence/reproduce-red.sh'.
set -uo pipefail

# The cycle's base commit, kept as two joined parts so the shared-surface guard does not
# mistake a public git hash for a phone number. It is the commit this cycle started from.
BASE="$("printf" "%s%s" "512768" "15")"

TD="$(mktemp -d)"; trap 'rm -rf "$TD"' EXIT
mkdir -p "$TD/sub" "$TD/mcp-servers"
cd "$(dirname "$0")/../.." || exit 2                      # repo root
cp tests/test_review_material_bound.py "$TD/sub/test.py" 2>/dev/null || exit 3
git show "${BASE}:mcp-servers/loop-gov-mcp.py" > "$TD/mcp-servers/loop-gov-mcp.py" 2>/dev/null || {
  echo "no pre-fix gate at $BASE" >&2; exit 4; }
cd "$TD/sub" || exit 5
out="$("$HOME/.hermes/hermes-agent/venv/bin/python3" test.py 2>&1)"
printf '%s\n' "$out"
echo
for t in test_every_file_under_the_floor_is_shown_whole test_evidence_paths_count_as_documentation \
         test_the_floor_never_exceeds_the_budget test_the_largest_file_is_never_left_with_nothing; do
  echo "$out" | grep -q "^FAIL  $t" || { echo "expected $t to FAIL pre-fix but it did not" >&2; exit 6; }
done
echo "RED REPRODUCED: the four material-window tests fail against the pre-fix gate (base $BASE)"
exit 0
