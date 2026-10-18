#!/usr/bin/env bash
# ensure-pytest.sh — make pytest importable on ANY host, through the repo's OWN declared set and
# the repo's OWN supply-chain age gate. One command, verified by IMPORT.
#
# WHY (adversarial findings ADV-13116-1 and ADV-13253-1, 2026-10-18). tests/run_loop_gov_regression.py
# has to JUDGE a pytest-style file, which it can only do with an interpreter that imports pytest.
# Resolving one that already exists is HALF the job: nothing in this repo CREATED one, so on a fresh
# host every pytest-style file was reported NOT RUN while the summary still printed a pass. The
# missing half is a create step, and it lives here rather than inside the harness so that every
# caller — the harness, a doctor check, a peer host's setup — runs the same three things:
#
#   1. the DECLARED dependency set  ops/install/requirements.txt      (pytest>=7.0 is declared there)
#   2. the canonical fleet venv     ~/.hermes-cortex/venv             (the venv cortex-update.sh
#                                                                      registers every MCP server against)
#   3. the SUPPLY-CHAIN age gate    ops/scripts/health/check-package-age.py
#
# Idempotent by IMPORT, not by metadata or an exit code: a venv that already imports pytest is left
# alone, and the installer is never invoked twice.
#
# USAGE
#   bash ops/scripts/lib/ensure-pytest.sh           # ensure it, then print the interpreter path
#   bash ops/scripts/lib/ensure-pytest.sh --check   # report only; never installs
#
# EXIT CODES
#   0  pytest is importable — the interpreter path is on stdout
#   1  the age gate refused, or the install ran and pytest is STILL not importable
#   2  usage error
#   3  COULD NOT VERIFY — a prerequisite is missing (no repair tool, or no age checker). Never a pass.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV="${PYTEST_VENV:-${HOME}/.hermes-cortex/venv}"
PY="${VENV}/bin/python3"
AGE_CHECK="${REPO}/ops/scripts/health/check-package-age.py"
VENV_FIX="${REPO}/ops/scripts/manage/fix-cortex-venv.py"
REQUIREMENTS="${REPO}/ops/install/requirements.txt"
MIN_AGE_DAYS="${MIN_AGE_DAYS:-14}"

check_only=0
case "${1:-}" in
  --check) check_only=1 ;;
  "") ;;
  *) echo "ensure-pytest: usage: $0 [--check]" >&2; exit 2 ;;
esac

# The capability test, run WITHOUT an inherited PYTHONPATH/PYTHONHOME: a foreign site-packages lands
# ahead of the venv's own and can make an empty venv look capable (measured on esther 2026-10-13).
imports_pytest() {
  [[ -x "$PY" ]] || return 1
  env -u PYTHONPATH -u PYTHONHOME "$PY" -c 'import pytest' >/dev/null 2>&1
}

if imports_pytest; then
  echo "$PY"
  exit 0
fi

echo "ensure-pytest: ${PY} does not import pytest" >&2
echo "  declared set: ${REQUIREMENTS}" >&2
if [[ "$check_only" == "1" ]]; then
  echo "  --check: reporting only — nothing installed" >&2
  exit 1
fi

for f in "$AGE_CHECK" "$VENV_FIX"; do
  if [[ ! -f "$f" ]]; then
    echo "ensure-pytest: COULD NOT VERIFY — missing prerequisite: $f" >&2
    echo "  Deploy the repo first (bash ops/scripts/update.sh or ops/scripts/cortex-update.sh)," >&2
    echo "  then re-run. Nothing was installed." >&2
    exit 3
  fi
done

echo "ensure-pytest: age gate — pip pytest must be at least ${MIN_AGE_DAYS} days old" >&2
python3 "$AGE_CHECK" --min-days "$MIN_AGE_DAYS" pip pytest >&2
rc_age=$?
if [[ "$rc_age" -ne 0 ]]; then
  echo "ensure-pytest: AGE GATE REFUSED (rc=${rc_age}) — not installing a package this new." >&2
  echo "  Wait out the window, or pin an older version in ${REQUIREMENTS}." >&2
  exit 1
fi

echo "ensure-pytest: installing the declared set into ${VENV}" >&2
python3 "$VENV_FIX"
rc_fix=$?
if [[ "$rc_fix" -ne 0 ]]; then
  echo "ensure-pytest: the venv repair FAILED (rc=${rc_fix}) — see its output above" >&2
  exit 1
fi

if imports_pytest; then
  echo "$PY"
  exit 0
fi

echo "ensure-pytest: the install ran and ${PY} STILL cannot import pytest — not a pass." >&2
echo "  Check the venv by hand: ${PY} -c 'import pytest'" >&2
exit 1
