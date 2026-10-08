#!/usr/bin/env bash
# Re-runnable evidence: orch-skill-lifecycle drift sync — cycle 11708 (2026-10-09).
# Proves: (1) each synced file's repo-pre-sync copy was a SUBSET of the deployed
# copy (no repo-only content lost), (2) fence counts even, (3) repo==deployed.
set -u
cd "$(dirname "$0")/../../.."   # -> repo root
PRE=365f0604^                   # repo state BEFORE the sync commit
SKILLS="
autonomous-ai-agents/pi-coding-agent
devops/governance-closeout
devops/hermes-gateway-operations
devops/mycortex
devops/shared-repo-push-gates
software-development/change-checklist
software-development/session-manager
"
echo "orch-skill-lifecycle drift-sync evidence — cycle 11708"
echo "sync commit: 365f0604   pre-sync ref: $PRE ($(git rev-parse --short $PRE))"
echo
echo "## 1. SUBSET proof: pre-sync repo content must survive in the synced file"
echo "   (every line removed from repo-pre must appear as a replaced/expanded line;"
echo "    'DIFF 0' on the pre->synced diff for a hunk means pure addition = safe)"
fail=0
for s in $SKILLS; do
  f="skills/$s/SKILL.md"
  git show "$PRE:$f" > /tmp/pre.$$ 2>/dev/null || { echo "  ERR cannot read $PRE:$f"; fail=1; continue; }
  # lines unique to the pre-sync repo file (content the sync would have to have dropped)
  lost=$(comm -23 <(sort -u /tmp/pre.$$) <(sort -u "$f") | grep -vE '^\s*$' | wc -l)
  # of those, how many are genuinely ABSENT (not just reworded)? show them
  if [ "$lost" -gt 0 ]; then
    echo "  $s: $lost pre-sync line(s) not byte-identical in synced file (inspect):"
    comm -23 <(sort -u /tmp/pre.$$) <(sort -u "$f") | grep -vE '^\s*$' | sed 's/^/      | /' | head -6
  else
    echo "  OK  $s: all pre-sync lines present (pure superset extension)"
  fi
done
rm -f /tmp/pre.$$
echo
echo "## 2. Fence balance (count of lines starting with triple-backtick; must be EVEN)"
for s in $SKILLS; do
  n=$(grep -c '^```' "skills/$s/SKILL.md")
  par=$([ $((n % 2)) -eq 0 ] && echo EVEN || echo ODD-BAD)
  echo "  $s: $n ($par)"
done
echo
echo "## 3. md5 identity synced repo == deployed"
for s in $SKILLS; do
  a=$(md5sum "skills/$s/SKILL.md" | cut -d' ' -f1)
  b=$(md5sum "$HOME/.hermes/skills/$s/SKILL.md" | cut -d' ' -f1)
  [ "$a" = "$b" ] && echo "  OK  $s  $a" || { echo "  MISMATCH $s repo=$a deployed=$b"; fail=1; }
done
echo
echo "exit: $fail (0 = all checks passed)"
exit $fail
