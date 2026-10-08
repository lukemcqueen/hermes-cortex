#!/usr/bin/env bash
# Review-material per-file bound — evidence for cycle #11253 (commit bde4e24d).
#
# Re-runnable: reproduces every claim made in the cycle note at the named revision.
#     bash ops/scripts/quality/evidence-review-material-per-file.sh \
#       > docs/evidence/review-material-per-file.txt
#
# Assertions are emitted FIRST, then the raw transcript, so the load-bearing lines
# cannot be lost if the material bound cuts this artifact.
set -uo pipefail
REPO="${HOME}/hermes-cortex"
REV="bde4e24d"
FAIL=0

hr() { printf '\n===== %s =====\n' "$1"; }
chk() { # name, expected, actual
  if [[ "$2" == "$3" ]]; then printf 'PASS  %s = %s\n' "$1" "$3"
  else printf 'FAIL  %s: expected %s got %s\n' "$1" "$2" "$3"; FAIL=1; fi
}

cd "$REPO" || exit 2

# ── assertions first ────────────────────────────────────────────────────────────
hr "ASSERTIONS"
BOUND_OUT="$(timeout 200 python3 tests/test_review_material_bound.py 2>&1 | grep -vE '^\[mcp-server\]')"
chk "bound test result" "RESULT: ALL PASS (12 tests)" "$(printf '%s\n' "$BOUND_OUT" | tail -1)"
chk "per-file regression case ran" "1" \
  "$(printf '%s\n' "$BOUND_OUT" | grep -c 'all 24 files present with body')"
chk "parity test result" "RESULT: ALL PASS (1 tests)" \
  "$(timeout 300 python3 tests/test_skill_drift_parity.py 2>&1 | tail -1)"
chk "A4 gate" "1" \
  "$(timeout 300 python3 "${HOME}/.hermes-cortex/scripts/adversarial-verify.py" \
      --file mcp-servers/loop-gov-mcp.py --level A4 --gate 2>&1 | grep -c 'GATE_PASSED')"
chk "harness artifact says ALL PASS" "1" \
  "$(grep -c '^RESULT: ALL PASS' tests/artifacts/loop-gov-regression.txt)"
chk "harness artifact covers 18 files" "18" \
  "$(grep -oE 'TEST SET \([0-9]+ files\)' tests/artifacts/loop-gov-regression.txt \
      | grep -oE '[0-9]+' | head -1)"
chk "harness artifact names this revision" "1" \
  "$(grep -c "revision .*: ${REV}" tests/artifacts/loop-gov-regression.txt)"

# ── the revision this ran against ───────────────────────────────────────────────
hr "revision"
echo "named revision: $REV"
git log --oneline -1 "$REV"
echo "HEAD=$(git rev-parse --short HEAD)"
echo "origin/main=$(git rev-parse --short origin/main)"

# ── the tested artifacts, pinned by hash (a partial diff verifies by hash) ──────
hr "tested artifacts (sha256)"
for f in mcp-servers/loop-gov-mcp.py tests/test_review_material_bound.py \
         tests/test_skill_drift_parity.py \
         skills/devops/governance-closeout/references/adversarial-gate-material.md \
         tests/run_loop_gov_regression.py; do
  printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
done

# ── raw transcript ──────────────────────────────────────────────────────────────
hr "raw: python3 tests/test_review_material_bound.py"
printf '%s\n' "$BOUND_OUT"
hr "raw: python3 tests/run_loop_gov_regression.py (committed artifact, tail)"
tail -5 tests/artifacts/loop-gov-regression.txt

hr "FINAL"
if [[ "$FAIL" == "0" ]]; then echo "RESULT: all assertions PASS"; else echo "RESULT: FAILURES present"; fi
exit "$FAIL"
