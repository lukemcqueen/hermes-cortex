#!/usr/bin/env bash
# Evidence capture — reviewer REFERENCE rule (cycle 13359, 2026-10-19).
#
# What it records, so the change is checkable rather than described:
#   1. the rule is in the SHIPPED template (the file the gate reads), not only in a doc;
#   2. the pinned test passes, including the strict-case (no-relaxation) assertions;
#   3. the rule names WHY the forbidden demand is unsatisfiable (the recursion).
#
# $HOME is redacted at the generator: this transcript lands in a public repo.
set -uo pipefail
exec > >(sed -u "s|${HOME}|~|g") 2>&1

REPO="${REPO:-$HOME/hermes-cortex}"
PY="$HOME/.hermes-cortex/venv/bin/python3"
cd "$REPO" || exit 1
TPL="docs/templates/adversarial-reviewer-prompt.md"

echo "=== reviewer REFERENCE rule — evidence (cycle 13359) ==="
echo "date: $(date -Is)"
echo

echo "--- 1. the rule, as shipped in the template the gate reads ---"
awk '/^## A reference to another file is a POINTER/,/^## Findings format/' "$TPL"
echo

echo "--- 2. the pinned tests (incl. the no-relaxation assertions) ---"
if [[ -x "$PY" ]]; then
  "$PY" -m pytest tests/test_review_policy_scope.py -q 2>&1 | tail -3
else
  echo "SKIP: $PY not found"
fi
echo

echo "--- 3. the strict case is still present verbatim (no lessening) ---"
grep -n "does NOT relax" "$TPL"
grep -n "committed, re-runnable test or script, in this range" "$TPL"
echo

echo "--- 4. the rule's teeth: what is still a REAL finding ---"
grep -n "invalidates" "$TPL"
echo

echo "--- 5. where the policy is documented ---"
grep -n "Reference rule" docs/design/independent-adversarial-verifier.md
echo
echo "=== end ==="
