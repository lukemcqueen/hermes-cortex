#!/usr/bin/env bash
# Re-runnable evidence for orch-skill-lifecycle cycle 11708, PHASE 2 evaluation.
# Supports the conclusion: no SOUL.md change, no prune, no upstream actions.
set -u
cd "$(dirname "$0")/../../.."

echo "=== A. Learning reports: staged inventory ==="
echo "  staged reports total: $(ls ~/.hermes-cortex/state/learning-reports/*.md 2>/dev/null | wc -l)"
echo "  newest 5 staged:"
ls -t ~/.hermes-cortex/state/learning-reports/*.md 2>/dev/null | head -5 | sed 's/^/    /'
echo "  [NEW]/[MOD] skill signals in newest 30 staged reports (deduped):"
for f in $(ls -t ~/.hermes-cortex/state/learning-reports/*.md 2>/dev/null | head -30); do
  grep -hoE '\[(NEW|MOD)\] [A-Za-z0-9._-]+ \([a-z-]+\)' "$f" 2>/dev/null
done | sort -u | sed 's/^/    /'

echo
echo "=== B. Learning ledger: pending items ==="
python3 ops/scripts/manage/learning-ledger.py list --status pending 2>&1 | sed 's/^/  /'

echo
echo "=== C. SOUL.md evaluation (cortex-doctor) ==="
python3 ops/scripts/manage/cortex-doctor.py 2>&1 | grep -iE 'SOUL' | sed 's/^/  /'

echo
echo "=== D. Repo skill inventory ==="
echo "  repo SKILL.md count: $(find skills -name SKILL.md | wc -l)"
echo "  skill drift (doctor):"
python3 ops/scripts/manage/cortex-doctor.py 2>&1 | grep -iE 'Skill drift' | sed 's/^/    /'
echo "  (Full staleness/prune pass runs on Monday deep-eval; today is a daily run.)"

echo
echo "exit: 0"
