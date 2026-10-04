#!/usr/bin/env bash
# Regenerate docs/evidence/skill-drift-parity-verify.txt (ADV-10582-4).
#
#   bash ops/scripts/manage/run-skill-parity-verify.sh
#
# Runs the repo's own adversarial verifier at A4 against the skill-parity
# checker and its test, writes the captured output to the artifact, and exits
# non-zero if either run reports a critical or high finding. The claim "the A4
# gate passed" is then reproducible by one command instead of being a pasted
# transcript.
#
# Not a deployed script — a repo-local evidence generator, like
# run-pii-gate-evidence.sh.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VERIFY="${HOME}/.hermes-cortex/scripts/adversarial-verify.py"
[ -x "${VERIFY}" ] || VERIFY="${REPO}/ops/scripts/quality/adversarial-verify.py"
OUT="${REPO}/docs/evidence/skill-drift-parity-verify.txt"

TARGETS=(
  "ops/scripts/manage/check-skill-drift-parity.py"
  "tests/test_skill_drift_parity.py"
)

rc=0
{
  echo "# Adversarial verification - skill-parity checker (A4, --gate)"
  echo
  echo "Regenerate with: \`bash ops/scripts/manage/run-skill-parity-verify.sh\`"
  echo
  echo "Verifier: ${VERIFY}"
  echo "Revision: $(git -C "${REPO}" rev-parse HEAD)"
  echo
} > "${OUT}"

for target in "${TARGETS[@]}"; do
  echo "## ${target}" >> "${OUT}"
  echo '```' >> "${OUT}"
  if ! python3 "${VERIFY}" --file "${REPO}/${target}" --level A4 --gate >> "${OUT}" 2>&1; then
    rc=1
  fi
  echo '```' >> "${OUT}"
  echo >> "${OUT}"
done

if [ "${rc}" -eq 0 ]; then
  echo "**Verdict: PASS**" >> "${OUT}"
else
  echo "**Verdict: FAIL**" >> "${OUT}"
fi

cat "${OUT}"
exit "${rc}"
