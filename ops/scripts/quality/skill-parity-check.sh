#!/usr/bin/env bash
# skill-parity-check.sh — prove a repo skill copy and its deployed copy are byte-identical.
#
# Why this exists: the "write-verify parity" rule requires a lesson applied to a DEPLOYED
# skill to be written back to the repo source, or the next deploy silently drops it. A diff
# printed to a terminal is not evidence a reviewer can re-run, so this script IS the evidence:
# it prints one CHECK line per pair with the byte counts, and exits non-zero on the first drift.
#
# Usage: skill-parity-check.sh [<repo-relative-skill-dir> ...]
#   with no argument it checks every skill in skills/hermes-agent/ that exists in both trees.

set -uo pipefail
REPO="${CORTEX_REPO:-/home/esther/hermes-cortex}"
DEPLOYED="${HERMES_HOME:-$HOME/.hermes}/skills"

pairs=("$@")
if [[ ${#pairs[@]} -eq 0 ]]; then
  while IFS= read -r d; do pairs+=("$d"); done < <(cd "$REPO" && find skills/hermes-agent -name SKILL.md -printf '%h\n' | sort)
fi

fail=0
for rel in "${pairs[@]}"; do
  rel="${rel#skills/}"
  a="$REPO/skills/$rel/SKILL.md"
  b="$DEPLOYED/$rel/SKILL.md"
  if [[ ! -f "$a" || ! -f "$b" ]]; then
    echo "SKIP  $rel — missing on one side (repo=$([[ -f $a ]] && echo yes || echo no) deployed=$([[ -f $b ]] && echo yes || echo no))"
    fail=1
    continue
  fi
  if cmp -s "$a" "$b"; then
    echo "CHECK $rel — byte-identical ($(wc -c < "$a") bytes)"
  else
    echo "DRIFT $rel — repo $(wc -c < "$a") bytes vs deployed $(wc -c < "$b") bytes"
    diff "$a" "$b" | head -20
    fail=1
  fi
done
echo "rc=$fail"
exit $fail
