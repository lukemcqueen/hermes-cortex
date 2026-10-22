#!/usr/bin/env bash
# The supported way to run a test suite: interpreter by CAPABILITY, environment CLEANSED.
#
# Why the cleansing is not optional. Same command, same host, ONLY the environment differing:
#
#   caller's PYTHONPATH inherited       1818 collected, 4 collection ERRORS
#   env -u PYTHONPATH -u PYTHONHOME     1846 collected, no errors
#
# Whole test modules failed to IMPORT, so their tests were absent from the run — and the
# runner printed "N passed" regardless. A foreign site-packages shadowing the venv's own
# build raises `ImportError` that reads like a broken host instead of a contaminated
# caller. Since an agent shell usually exports PYTHONPATH, contaminated is the DEFAULT case.
#
# Usage: run-tests.sh [pytest args...]      (default: tests/ -q)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Interpreter by capability, not by path: a path is not a promise.
PY=""
if [ -n "${CORTEX_PYTHON:-}" ] && "$CORTEX_PYTHON" -c 'import pytest' 2>/dev/null; then
  PY="$CORTEX_PYTHON"
elif [ -x "${HOME}/.hermes-cortex/venv/bin/python3" ] && \
     "${HOME}/.hermes-cortex/venv/bin/python3" -c 'import pytest' 2>/dev/null; then
  PY="${HOME}/.hermes-cortex/venv/bin/python3"
fi
if [ -z "$PY" ]; then
  # Not a fleet host, or a repo with its own interpreter: probe PATH by CAPABILITY. "python3
  # exists" is not "pytest is importable", so still run an import test — and SAY that you fell
  # back, because a silent fallback swaps which code decides the interpreter while the run looks
  # identical (it can even make a stub test exercise the real thing and "pass").
  for _c in python3 python; do
    if command -v "$_c" >/dev/null 2>&1; then
      if env -u PYTHONPATH -u PYTHONHOME "$_c" -c 'import pytest' >/dev/null 2>&1; then
        PY="$(command -v "$_c")"
        echo "note: no fleet interpreter usable here; using $_c from PATH, which CAN import pytest" >&2
        break
      fi
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "COULD NOT VERIFY: no interpreter on this host can import pytest." >&2
  echo "  Tried the declared/fleet interpreters, then python3/python on PATH." >&2
  echo "  No interpreter means no verdict — this is NOT a pass." >&2
  exit 3
fi

ARGS=("$@")
if [ "${#ARGS[@]}" -eq 0 ]; then
  ARGS=(tests/ -q)
else
  # pytest with only FLAGS and no PATH collects the entire current directory (in a repo:
  # .git, deploy trees, the venv) and hangs. If the caller named no selection, supply one.
  case " $* " in
    *" tests"*|*" tests/"*|*"/*"*|*"::"*|*"*.py"*) : ;;
    *) ARGS=("${ARGS[@]}" tests/) ;;
  esac
fi

# bash 3.2 (macOS) ERRORS on an empty-array expansion under `set -u`, hence the guard above.
# env -u: the interpreter must not inherit the caller's view of where packages live.
env -u PYTHONPATH -u PYTHONHOME "$PY" -m pytest "${ARGS[@]}" -p no:cacheprovider
rc=$?

# Capture the rc BARE, in the VERY NEXT statement, and print it: `cmd | tail -1` prints the last
# line whatever happened above it, and `PIPESTATUS` is reset by every command, so any echo in
# between leaves it empty (`rc=` in the artifact reads as zero-or-unknown).
echo "---"
echo "run-tests.sh: interpreter=$PY rc=$rc  (PYTHONPATH/PYTHONHOME unset for the run)"
exit $rc
