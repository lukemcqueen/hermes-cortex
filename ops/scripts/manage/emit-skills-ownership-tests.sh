#!/usr/bin/env bash
# Regenerate the skills-ownership test transcript (cycle 13491).
#
# CHECKOUT-ONLY — run-scoped evidence tooling, deliberately not in cortex-update.sh
# register(): a host does not need it to stay healthy. The tools under test ARE registered
# (ops/scripts/manage/migrate-skills-ownership.py, ops/scripts/manage/publish-agent-skills.py).
#
# Usage:  bash ops/scripts/manage/emit-skills-ownership-tests.sh [output-file]
# Exit:   the pytest status (0 = all passed) — never a false green.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../../.." && pwd)"   # manage -> scripts -> ops -> repo root
# Interpreter: the fleet venv is the one that HAS pytest. Never fall back silently to a
# python3 that cannot run the suite — that produced 'No module named pytest' reported as a
# successful transcript once (2026-10-21), the very swallowed-error class under review.
if [ -n "${CORTEX_PY:-}" ]; then
  PY="$CORTEX_PY"
elif [ -x "${HOME}/.hermes-cortex/venv/bin/python3" ]; then
  PY="${HOME}/.hermes-cortex/venv/bin/python3"
else
  PY="python3"
fi
OUT="${1:-${REPO}/docs/evidence/skills-ownership-tests-$(date -u +%Y-%m-%d).txt}"

cd "$REPO" || exit 3

if ! "$PY" -c "import pytest" >/dev/null 2>&1; then
  echo "COULD NOT VERIFY: ${PY} cannot import pytest — set CORTEX_PY to one that can" >&2
  exit 3
fi

{
  echo "# skills-ownership + publish test transcript (cycle 13491)"
  echo "# regenerate with:  bash ops/scripts/manage/emit-skills-ownership-tests.sh"
  echo "# generated:        $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# subject:          ops/scripts/manage/migrate-skills-ownership.py"
  echo "#                   ops/scripts/manage/publish-agent-skills.py"
  echo "#"
  "$PY" -m pytest tests/test_skills_ownership.py tests/test_agent_skills_publish.py \
      -q --no-header -p no:randomly 2>&1 | sed -e "s|${HOME}|~|g"
  pytest_rc="${PIPESTATUS[0]}"   # pytest's own status, read BEFORE any other command runs
  # The interpreter line is redacted too: it is a $HOME path and this repo is public
  # (self-adversarial PII class, flagged twice on this cycle).
  printf 'interpreter: %s\n' "${PY}" | sed -e "s|${HOME}|~|g"
  echo "PYTEST rc=${pytest_rc} (0 = all passed)"
} > "${OUT}.tmp"

mv "${OUT}.tmp" "$OUT"
echo "transcript written: ${OUT}"
# Exit with PYTEST's status, never the echo's: an emitter that reports success for a suite
# that did not run is the false-green class this file exists to avoid.
exit "${pytest_rc:-3}"
