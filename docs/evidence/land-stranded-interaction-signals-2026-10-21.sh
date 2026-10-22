#!/usr/bin/env bash
# Evidence: the verbosity lesson was stranded in the DEPLOYED skills tree only; it is now in the
# repo source (the tree the fleet is published from), with the two rules the 2026-10-21 window's
# corrections added.
#
# Re-run: bash docs/evidence/land-stranded-interaction-signals-2026-10-21.sh
# Every rc printed below is the rc of the command named beside it, captured WITHOUT a pipe.
set -u
REPO="${REPO:-$HOME/hermes-cortex}"
REL="skills/communication/agent-interaction-signals/SKILL.md"
DEPLOYED="$HOME/.hermes-cortex/skills/communication/agent-interaction-signals/SKILL.md"
cd "$REPO" || exit 2

echo "===== capture ====="
echo "date            : $(date -Is)"
echo "host            : $(uname -srm)"
echo "repo            : \$HOME/hermes-cortex @ $(git rev-parse --short HEAD)"
echo "repo copy       : $(wc -c < "$REL") bytes  sha256=$(sha256sum < "$REL" | cut -c1-16)"
echo "deployed copy   : $(wc -c < "$DEPLOYED") bytes  sha256=$(sha256sum < "$DEPLOYED" | cut -c1-16)"
cmp -s "$REL" "$DEPLOYED"
echo "cmp repo deployed: rc=$?  (0 = byte-identical, so the tree is in sync in BOTH directions)"
echo

echo "===== the stranded entry BEFORE this change (from check-skill-drift-parity.py) ====="
echo "| Stranded in place (path in repo, content only deployed) | 18 |"
echo "- communication/agent-interaction-signals/SKILL.md"
echo "# ^ the lesson the operator gave at 10:54 (\"please less prose and just say things plainly\")"
echo "#   was written into the deployed copy only, so the deploy's drift guardrail refused to"
echo "#   overwrite it and the fleet never received it."
echo

echo "===== the repo change (only additions) ====="
git diff -U1 -- "$REL"
echo

echo "===== AFTER: re-run the fleet's own detector ====="
python3 ops/scripts/manage/check-skill-drift-parity.py > /tmp/parity-evidence.txt 2>&1
echo "detector rc=$?  (1 = other stranded skills remain, owned by the daily skill-lifecycle pass)"
grep -n "Stranded in place (path in repo" /tmp/parity-evidence.txt
echo "is the landed skill still listed as stranded?"
if sed -n '/Stranded in place:/,/Absent from the repo/p' /tmp/parity-evidence.txt | grep -q "^- communication/agent-interaction-signals/SKILL.md"; then
  echo "  YES — still stranded (the change did NOT land)"
else
  echo "  no — it is out of the stranded list (18 -> 17)"
fi
echo

echo "===== the operator corrections this artifact lands ====="
echo "10-21 10:54  please less prose and just say things plainly"
echo "10-21 15:47  so much text... sigh. please just give me your issues simply and the decisions needed"
echo "10-21 16:06  so you have bumped up the issue to the operator (me). so how would i resolve this?"
echo "10-21 16:35  what do you mean by: I'm at my budget wall"
echo "# the first is the stranded section; the other three are its two new rules (name the ask,"
echo "# name the observable fact) — read from the sessions store, window 10-20 17:18 -> 10-21 23:18."
echo
echo "===== end of transcript ====="
