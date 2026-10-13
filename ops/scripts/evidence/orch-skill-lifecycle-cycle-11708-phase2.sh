#!/usr/bin/env bash
# Re-runnable evidence for orch-skill-lifecycle cycle 11708, PHASE 2 evaluation.
# Supports the conclusion: no SOUL.md change, no prune, no upstream actions.
set -u
cd "$(dirname "$0")/../../.."

# The interpreter is resolved by CAPABILITY, not by PATH: cortex-doctor.py imports yaml, and in an
# agent session a bare `python3` can be a Hermes tools python with no yaml at all (measured
# 2026-10-13). Guarded by tests/test_direct_run_interpreter.py, which class-scans the repo.
DOCTOR_PY="$(bash ops/scripts/lib/python-with-module.sh --print yaml 2>/dev/null || true)"
if [[ -z "$DOCTOR_PY" ]]; then
  echo "  (no interpreter here can import yaml — cortex-doctor cannot run: COULD NOT VERIFY)"
  exit 0
fi

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
"$DOCTOR_PY" ops/scripts/manage/cortex-doctor.py 2>&1 | grep -iE 'SOUL' | sed 's/^/  /'

echo
echo "=== D. Repo skill inventory ==="
echo "  repo SKILL.md count: $(find skills -name SKILL.md | wc -l)"
echo "  skill drift (doctor):"
"$DOCTOR_PY" ops/scripts/manage/cortex-doctor.py 2>&1 | grep -iE 'Skill drift' | sed 's/^/    /'
echo "  (Full staleness/prune pass runs on Monday deep-eval; today is a daily run.)"

echo
echo "exit: 0"

# 2026-10-13: the interpreter here is resolved by capability (tests/test_direct_run_interpreter.py)
