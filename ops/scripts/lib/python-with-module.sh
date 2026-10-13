#!/usr/bin/env bash
# python-with-module.sh - run (or print) an interpreter that can IMPORT a given module.
#
# WHY THIS EXISTS (2026-10-08). Several scripts chose a python by PATH EXISTENCE and
# then fell back to a bare `python3`. That is wrong twice over:
#
#   * the file existing says NOTHING about the module being importable, and
#   * the fallback is usually the one interpreter known to lack it.
#
# Measured on esther:
#   ~/.hermes-cortex/venv/bin/python3      exists, imports yaml=NO  mcp=NO
#   ~/.hermes/hermes-agent/venv/bin/python3 exists, imports yaml=YES mcp=YES
#   python3 (the Hermes tools python on the cron PATH)  yaml=NO
#
# So orch-daily-regression-gate.sh's `if [[ ! -x $PY ]]` guard never fired, it ran the
# eval harness under a PyYAML-less interpreter, and the gate failed EVERY DAY with
# "PyYAML is not installed — cannot parse eval definitions" (a comment claiming "the
# cortex venv has PyYAML" is not a guard).
#
# USAGE
#   python-with-module.sh <module> <script> [args...]   # exec the first capable python
#   python-with-module.sh --print <module>              # print its path (for callers
#                                                       # that need the interpreter)
#
# EXIT CODES
#   the child's own code, or
#   2  usage error
#   3  COULD NOT VERIFY — no interpreter can import the module. Callers MUST treat 3 as
#      "cannot check", never as a negative result.
set -uo pipefail

print_only=0
if [[ "${1:-}" == "--print" ]]; then
  print_only=1
  shift
fi
module="${1:-}"
shift || true
if [[ -z "$module" ]]; then
  echo "python-with-module: usage: $0 [--print] <module> [args...]" >&2
  exit 2
fi

declared_python() {
  # ONE name for "the fleet interpreter", declared per host and overridable in the environment.
  # Callers read this instead of re-deriving a path, so there is one place to be wrong rather
  # than seven: on 2026-10-13 seven scripts each needed their own clean-env probe because the
  # agent session exported a foreign site-packages AND put a 3.14 tools python ahead of /usr/bin.
  [[ -n "${CORTEX_PYTHON:-}" ]] && printf '%s\n' "${CORTEX_PYTHON}"
  local f="${CORTEX_ENV_FILE:-${HOME}/.hermes-cortex/agent.env}"
  [[ -f "$f" ]] && sed -n 's/^CORTEX_PYTHON=//p' "$f" | head -1
}

candidates() {
  # An explicit choice wins, then the DECLARED fleet interpreter — the fleet venv this host runs
  # its services with (cortex-update.sh points every MCP registration at it) — then the Hermes
  # venv, then whatever is on PATH, then versioned names.
  #
  # Measured on esther 2026-10-13: ~/.hermes-cortex/venv imports yaml + mcp (and pytest once
  # installed there); ~/.hermes/hermes-agent/venv imports all three; the Hermes tools python
  # imports none. The ORDER only breaks ties — a module only the Hermes venv has still
  # resolves, because a candidate must import the module to be chosen. Putting the cortex
  # venv first keeps fleet tooling off the tree we are migrating away from, which is the
  # whole point of having a cortex venv at all.
  [[ -n "${PYTHON:-}" ]] && printf '%s\n' "$PYTHON"
  declared_python
  [[ -n "${HERMES_VENV:-}" ]] && printf '%s\n' "${HERMES_VENV}/bin/python3"
  printf '%s\n' "${HOME}/.hermes-cortex/venv/bin/python3"
  printf '%s\n' "${HOME}/.hermes/hermes-agent/venv/bin/python3"
  command -v python3 2>/dev/null || true
  local v
  for v in 3.14 3.13 3.12 3.11 3.10 3.9; do
    command -v "python${v}" 2>/dev/null || true
  done
}

# The module name is passed as ARGV, never interpolated into the code string.
#
# EVERY probe and the payload itself run WITHOUT an inherited PYTHONPATH/PYTHONHOME.
# Measured on esther 2026-10-13: the agent runtime exports a Python 3.14 site-packages from a
# Hermes-managed install environment, which lands ahead of a venv's own site-packages — so a
# capability probe can decide on the WRONG packages entirely (a venv that imports `mcp` fine
# read as broken, and a bare interpreter could look capable because a foreign path supplied the
# module). Choosing an interpreter is exactly the decision that must not depend on the caller's
# environment. `env -u` is POSIX, so this holds on Linux and macOS.
if [[ -n "${PYTHONPATH:-}${PYTHONHOME:-}" ]]; then
  echo "python-with-module: ignoring inherited PYTHONPATH/PYTHONHOME while choosing an interpreter — an inherited path can shadow the target's own packages" >&2
fi

tried=""
while IFS= read -r py || [[ -n "$py" ]]; do
  [[ -n "$py" ]] || continue
  command -v "$py" >/dev/null 2>&1 || continue
  case " ${tried} " in *" ${py} "*) continue ;; esac
  tried="${tried} ${py}"
  if env -u PYTHONPATH -u PYTHONHOME "$py" -c 'import importlib, sys; importlib.import_module(sys.argv[1])' "$module" \
       >/dev/null 2>&1; then
    if [[ "$print_only" == "1" ]]; then
      printf '%s\n' "$py"
      exit 0
    fi
    exec env -u PYTHONPATH -u PYTHONHOME "$py" "$@"
  fi
done < <(candidates)

{
  echo "python-with-module: COULD NOT VERIFY — no interpreter can import '${module}'."
  echo "  Checked:${tried}"
  _decl="$(declared_python | head -1)"
  if [[ -n "$_decl" ]]; then
    echo "  Declared CORTEX_PYTHON: ${_decl}"
    echo "    it cannot import '${module}' — a declaration is a promise. Fix it, or unset"
    echo "    CORTEX_PYTHON in ~/.hermes-cortex/agent.env to fall back to the built-in order."
  fi
  echo "  Fix one of:"
  echo "    - install ${module} for one of them        (e.g. python3 -m pip install ${module})"
  echo "    - point this wrapper at a capable one:"
  echo "        PYTHON=/path/to/python3 bash $0 ${module} ..."
} >&2
exit 3
