#!/usr/bin/env bash
# verify-dream-2026-10-12.sh — reproducible proof for the nightly mycortex
# dream digest (2026-10-12, Titus). Proves the scan surfaced the 2 Timothy
# page, the brain file exists with expected content, and the INDEX was
# appended. Every claim below asserts its own condition — no claim can fail
# silently while the script still reports PASS.
#
# A later reviewer can run this on the host (Luke's MacBook) to re-verify
# the dream write from cycle #5925 without trusting prose.
set -uo pipefail

BRAIN_FILE="$HOME/brain/titus/dreams/2026-10-12.md"
INDEX_FILE="$HOME/brain/titus/dreams/INDEX.md"
EXPECTED_BYTES=977
EXPECTED_FIRST="# Dream — 2026-10-12"

fail=0
check() { # check <description> <command...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "OK  $desc"; else echo "FAIL $desc"; fail=1; fi
}

# ── Dream-write proof ────────────────────────────────────────────────
check "brain file exists: $BRAIN_FILE"            test -f "$BRAIN_FILE"
if [ -f "$BRAIN_FILE" ]; then
  check "byte count == $EXPECTED_BYTES"           test "$(wc -c < "$BRAIN_FILE" | tr -d ' ')" = "$EXPECTED_BYTES"
  check "first line == '$EXPECTED_FIRST'"         test "$(head -1 "$BRAIN_FILE")" = "$EXPECTED_FIRST"
fi
check "INDEX has a 2026-10-12 entry"              grep -q "^2026-10-12 |" "$INDEX_FILE"

# ── Scan / search proof: MUST assert or the script fails (no swallowing) ─
check "mycortex list surfaces bible/2-timothy-2026-10-12.md" \
  sh -c 'mycortex list -n 20 2>&1 | grep -q "bible/2-timothy-2026-10-12.md"'
check "mycortex search returns 2-timothy @ score>=0.9" \
  sh -c 'score=$(mycortex search "rightly handle the word of truth" --limit 3 2>&1 | grep -oE "\[0\.[0-9]+\] bible/2-timothy-2026-10-12" | head -1 | grep -oE "0\.[0-9]+"); awk -v s="$score" "BEGIN{exit !(s>=0.9)}"'

# Exact INDEX entry + dream content assertion (so the evidence md quote is
# backed by the script, not just a prefix grep).
EXPECTED_INDEX="2026-10-12 | The truth, rightly handled |"
check "INDEX 2026-10-12 entry begins '$EXPECTED_INDEX'" \
  grep -q "$EXPECTED_INDEX" "$INDEX_FILE"
check "dream body contains 'rightly handle the word of truth' (2 Tim 2:15)" \
  grep -q "rightly handle the word of truth" "$BRAIN_FILE"
check "mycortex stats reports 0 failed syncs" \
  sh -c 'mycortex stats 2>&1 | grep -q "failed_syncs: 0"'

# ── Output raw values for the transcript (informational, already asserted) ─
echo "---"
echo "INDEX tail -1:"
tail -1 "$INDEX_FILE"
echo "---"
echo "mycortex search 'rightly handle the word of truth' (top hits):"
mycortex search "rightly handle the word of truth" --limit 3 2>&1 | head -3
echo "---"
echo "mycortex stats:"
mycortex stats 2>&1 | grep -E 'pages|chunks|failed' | head -3

echo "RESULT: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail
