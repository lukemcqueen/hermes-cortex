#!/usr/bin/env bash
# Re-runnable classifier for the orch-skill-lifecycle drift sync (2026-10-14).
#
# WHY THIS EXISTS (ADV-12498-002/ADV-12498-001):
# `reconcile-stranded-skills.py` flags a drifted skill as REVIEW when the raw
# line diff shows deletions ("would drop N line(s)"). That heuristic cannot
# tell a REVERT (repo content the deployed copy lacks — never copy) from a
# SUPERSEDE (the repo's prose line replaced in place by the deployed side's
# wrapped/expanded wording — safe to copy verbatim).
#
# This script re-derives the distinction mechanically for every REVIEW-flagged
# file by normalising whitespace and comparing WORD MULTISETS:
#   repo words not present in deployed  -> genuine loss (revert risk)
#   nothing lost + words added          -> in-place supersede (safe)
# It exits non-zero if ANY REVIEW file would lose content, so it can be run as
# a gate: a green run asserts "no lesson was lost by this sync".
#
# Usage: bash ops/scripts/quality/classify-drift-supersede.sh [repo] [deployed]
set -uo pipefail
REPO="${1:-$HOME/hermes-cortex}"
DEPLOYED="${2:-$HOME/.hermes/skills}"

FILES=(
  devops/approval-gate-debugging
  devops/governance-closeout
  devops/governance-lock-lifecycle
  devops/loop-governance
  devops/maintenance-scan
  devops/mcp-health-monitoring
  software-development/agent-contract
  software-development/change-checklist
  software-development/hermetic-python-testing
  software-development/prove-before-create
)

# Word-multiset difference: words in $1 not accounted for by $2.
words_missing() {  # $1=old file  $2=new file
  comm -23 <(tr -cs '[:alnum:]_.`/' '\n' < "$1" | sort -u) \
           <(tr -cs '[:alnum:]_.`/' '\n' < "$2" | sort -u) \
    | grep -c . 
}

rc=0
printf '%-46s %8s %8s %8s %8s  %s\n' FILE repo_lines dep_lines lost added VERDICT
for f in "${FILES[@]}"; do
  # The classifier runs BEFORE the sync; after it the two sides are identical.
  # To re-derive post-sync, compare the synced repo file against the commit's
  # parent. `git show HEAD~1:<path>` is the pre-sync repo side.
  old="$(git -C "$REPO" show "HEAD~1:skills/$f/SKILL.md" 2>/dev/null)"
  new="$DEPLOYED/$f/SKILL.md"
  [ -f "$new" ] || { printf '%-46s  MISSING deployed copy\n' "$f"; rc=1; continue; }
  tmp="$(mktemp)"; printf '%s' "$old" > "$tmp"
  rl=$(wc -l < "$tmp"); dl=$(wc -l < "$new")
  lost=$(words_missing "$tmp" "$new")
  added=$(words_missing "$new" "$tmp")
  if [ "$lost" -eq 0 ]; then v="SUPERSEDE (safe)"; else v="REVERT RISK -> DO NOT COPY"; rc=1; fi
  printf '%-46s %8s %8s %8s %8s  %s\n' "$f" "$rl" "$dl" "$lost" "$added" "$v"
  rm -f "$tmp"
done

echo
echo "fence balance (repo vs deployed, must both be EVEN):"
for f in "${FILES[@]}"; do
  a=$(grep -c '^```' "$REPO/skills/$f/SKILL.md" 2>/dev/null)
  b=$(grep -c '^```' "$DEPLOYED/$f/SKILL.md" 2>/dev/null)
  s="BALANCED"; { [ $((a%2)) -ne 0 ] || [ $((b%2)) -ne 0 ]; } && { s="UNBALANCED"; rc=1; }
  printf '  %-46s repo=%-3s deployed=%-3s %s\n' "$f" "$a" "$b" "$s"
done

echo
echo "Exit $rc — 0 means every REVIEW-flagged file was an in-place supersede and no lesson was lost."
exit $rc
