#!/usr/bin/env bash
# Run the fleet test suite with an interpreter chosen by CAPABILITY and an environment CLEANSED of
# the caller's PYTHONPATH/PYTHONHOME.
#
# Why the cleansing is not optional — measured on this fleet 2026-10-13, same command, same host,
# ONLY the environment differing:
#
#   caller's PYTHONPATH inherited       1817 collected, 4 collection ERRORS
#   env -u PYTHONPATH -u PYTHONHOME     1845 collected, no errors
#
# 28 tests were silently absent and 4 modules did not import at all — `No module named
# 'pydantic_core._pydantic_core'`, a FOREIGN site-packages shadowing the fleet venv's own build.
# That is an ABI mismatch, not a missing dependency, and the runner printed "N passed" either way.
# Since every agent session inherits a PYTHONPATH, the contaminated case is the DEFAULT case.
#
# Usage: tests/run-tests.sh [pytest args...]     (default: tests/ -q)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Interpreter by CAPABILITY, like every other probe in this fleet: a path is not a promise.
RESOLVER="$REPO/ops/scripts/lib/python-with-module.sh"
if [ -x "$RESOLVER" ]; then
  :
else
  RESOLVER="${HOME}/.hermes-cortex/scripts/lib/python-with-module.sh"
  # Say so. A silent fallback swaps WHICH resolver decides the interpreter, which is exactly the
  # kind of substituted signal this fleet keeps getting bitten by: the run looks identical and is
  # running different code.
  echo "note: no executable repo resolver at \$REPO/ops/scripts/lib/python-with-module.sh" >&2
  echo "      falling back to the deployed one: $RESOLVER" >&2
fi

PY=""
if [ -x "$RESOLVER" ]; then
  PY="$(PYTHON= "$RESOLVER" --print pytest 2>/dev/null)" || true
fi
if [ -z "$PY" ]; then
  # Non-cortex repo, or a host with no fleet install: the resolver has nothing to read. Fall back to
  # a CAPABILITY probe on PATH — still a capability probe, never a bare path (the whole point is
  # that "python3 exists" is not "pytest is importable"), and still with the environment cleansed
  # so the answer does not depend on the caller.
  for _c in python3 python; do
    if command -v "$_c" >/dev/null 2>&1; then
      if env -u PYTHONPATH -u PYTHONHOME "$_c" -c 'import pytest' >/dev/null 2>&1; then
        PY="$(command -v "$_c")"
        echo "note: no fleet resolver usable here; using $_c from PATH, which CAN import pytest" >&2
        break
      fi
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "COULD NOT VERIFY: no interpreter on this host can import pytest." >&2
  echo "  Tried: ${RESOLVER} (and the repo copy), then python3/python on PATH" >&2
  echo "  Fix:   ${HOME}/.hermes-cortex/scripts/manage/fix-cortex-venv.py" >&2
  echo "  No interpreter means no verdict — this is NOT a pass." >&2
  exit 3
fi

ARGS=("$@")
if [ "${#ARGS[@]}" -eq 0 ]; then
  ARGS=(tests/ -q)
else
  # pytest with only FLAGS and no PATH collects the entire current directory — which here means
  # .git, deploy trees and the venv, and it hangs (measured: 400s+ with no output). If the caller
  # named no test selection, supply the suite.
  case " $* " in
    *" tests"*|*" tests/"*|*"/*"*|*"::"*|*".py"*) : ;;
    *) ARGS=("${ARGS[@]}" tests/) ;;
  esac
fi

# env -u: the interpreter must not inherit the caller's view of where packages live.
env -u PYTHONPATH -u PYTHONHOME "$PY" -m pytest "${ARGS[@]}" -p no:cacheprovider
rc=$?

echo "---"
echo "run-tests.sh: interpreter=$PY rc=$rc  (PYTHONPATH/PYTHONHOME unset for the run)"
exit $rc