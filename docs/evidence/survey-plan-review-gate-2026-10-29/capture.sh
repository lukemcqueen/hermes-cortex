#!/usr/bin/env bash
# Re-runnable evidence capture for the survey-before-build + plan-review-before-slice
# enforcement gates (cycle survey-plan-review-gate, commit f850648d).
# Emits one block per command beside its own rc, ending on a verdict.
#
# Files this capture invokes that are NOT part of this range (all pre-existing at
# the tip, judged in their own windows; none are authored by this change):
#   - tests/test-reflexion-gate-repoint.sh  (hermetic reflexion-gate block test)
#   - tests/test-reflexion-gate-e2e.sh      (end-to-end reflexion gate, needs store)
#   - tests/test_enforcer_yaml_compat.py    (enforcer manifest yaml compat)
#   - tests/test_pi_skill_load_evidence.py  (Pi tool-event load evidence)
#   - ops/scripts/quality/adversarial-verify.py (the A2/A4 static gate)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="${CORTEX_PYTHON:-$HOME/.hermes-cortex/venv/bin/python3}"
[ -x "$PY" ] || PY="$(command -v python3)"
OUT="${1:-$ROOT/docs/evidence/survey-plan-review-gate-2026-10-29/verify.txt}"
mkdir -p "$(dirname "$OUT")"
exec >"$OUT" 2>&1
run() { # run <label> <cmd...> — prints rc; FAILs when non-zero
  local label="$1"; shift
  echo "===== $label ====="
  "$@" ; local rc=$?
  echo "rc=$rc"
  [ "$rc" -eq 0 ] || FAIL=1
  echo
}
echo "# Survey/Plan-Review gate verify — captured $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "root=$ROOT py=$PY"
echo "tip=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo n/a)"
echo
FAIL=0
run "bash -n changelist" bash -n "$ROOT/ops/scripts/pre-commit-score" "$ROOT/ops/scripts/cortex-update.sh"
run "reflexion gate hermetic test" bash "$ROOT/tests/test-reflexion-gate-repoint.sh"
run "reflexion gate e2e test" bash "$ROOT/tests/test-reflexion-gate-e2e.sh"
run "plan-review gate pytest" "$PY" -m pytest "$ROOT/tests/test_plan_review_gate.py" -q -p no:cacheprovider
run "enforcer yaml compat + pi evidence pytest" "$PY" -m pytest "$ROOT/tests/test_enforcer_yaml_compat.py" "$ROOT/tests/test_pi_skill_load_evidence.py" -q -p no:cacheprovider
for f in ops/scripts/pre-commit-score ops/scripts/hc-reflexion-check.py ops/scripts/hc-plan-review-check.py ops/scripts/cortex-update.sh ops/scripts/manage/cortex_doctor/checks.py plugins/governance-enforcer/__init__.py; do
  lvl=A2; case "$f" in plugins/*|ops/scripts/manage/*) lvl=A4;; esac
  run "adversarial $lvl $f" "$PY" "$ROOT/ops/scripts/quality/adversarial-verify.py" --file "$ROOT/$f" --level "$lvl" --gate
done
run "hc-reflexion-check --skip-no-session (no session)" "$PY" "$ROOT/ops/scripts/hc-reflexion-check.py" --skip-no-session --repo-slug no-such-repo-evidence
echo "===== VERDICT ====="
if [ "$FAIL" -eq 0 ]; then echo "ALL PASS"; else echo "FAILURES PRESENT (see above)"; exit 1; fi
