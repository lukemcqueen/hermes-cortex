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

candidates() {
  # An explicit choice wins, then the fleet venv this host actually runs services with,
  # then the cortex venv, then whatever is on PATH, then versioned names — a host may
  # have the module in only one of them.
  [[ -n "${PYTHON:-}" ]] && printf '%s\n' "$PYTHON"
  [[ -n "${HERMES_VENV:-}" ]] && printf '%s\n' "${HERMES_VENV}/bin/python3"
  printf '%s\n' "${HOME}/.hermes/hermes-agent/venv/bin/python3"
  printf '%s\n' "${HOME}/.hermes-cortex/venv/bin/python3"
  command -v python3 2>/dev/null || true
  local v
  for v in 3.14 3.13 3.12 3.11 3.10 3.9; do
    command -v "python${v}" 2>/dev/null || true
  done
}

# The module name is passed as ARGV, never interpolated into the code string.
tried=""
while IFS= read -r py || [[ -n "$py" ]]; do
  [[ -n "$py" ]] || continue
  command -v "$py" >/dev/null 2>&1 || continue
  case " ${tried} " in *" ${py} "*) continue ;; esac
  tried="${tried} ${py}"
  if "$py" -c 'import importlib, sys; importlib.import_module(sys.argv[1])' "$module" \
       >/dev/null 2>&1; then
    if [[ "$print_only" == "1" ]]; then
      printf '%s\n' "$py"
      exit 0
    fi
    exec "$py" "$@"
  fi
done < <(candidates)

{
  echo "python-with-module: COULD NOT VERIFY — no interpreter can import '${module}'."
  echo "  Checked:${tried}"
  echo "  Fix one of:"
  echo "    - install ${module} for one of them        (e.g. python3 -m pip install ${module})"
  echo "    - point this wrapper at a capable one:"
  echo "        PYTHON=/path/to/python3 bash $0 ${module} ..."
} >&2
exit 3
