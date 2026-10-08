#!/usr/bin/env bash
# gen-skills-manifest.sh - run the manifest generator under an interpreter that
# actually has PyYAML.
#
# WHY THIS EXISTS (2026-10-08). The generator parses `skills/**/SKILL.md`
# frontmatter with `yaml.safe_load`, so it needs a real YAML parser: the
# frontmatter uses block scalars (`description: >-`), and a regex fallback would
# silently misread descriptions into the manifest. THREE call sites invoked it as
# a bare `python3`:
#
#   ops/scripts/pre-commit-doc-audit.sh                     the freshness gate
#   ops/scripts/manage/verify-skill-lifecycle-run.py        the lifecycle check
#   gen-skills-manifest.py's own error message              the remedy it prints
#
# On a host whose default `python3` has no PyYAML (esther: the Hermes tools
# python) the generator dies with "ModuleNotFoundError: No module named 'yaml'".
# The gate read that as CHECK-FAILED and reported the manifest as STALE on every
# commit that touched skills/ - a false accusation - while the remedy it printed
# was the same command that could not run. One wrong interpreter, so a dead end
# AND a false positive.
#
# The interpreter choice now lives here and nowhere else: every caller runs this
# wrapper. Exit codes match the generator's own - 0 = fresh, 1 = would change
# (stale), 2 = usage error, 3 = COULD NOT VERIFY (no interpreter with PyYAML).
# Callers MUST treat 3 as "cannot check", never as "stale".
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gen="$here/gen-skills-manifest.py"

candidates() {
    # An explicit choice wins, then the Hermes venv (the interpreter this fleet
    # actually runs its cortex services with), then whatever python3 is on PATH,
    # then versioned names - a host may have PyYAML in only one of them.
    if [[ -n "${PYTHON:-}" ]]; then printf '%s\n' "$PYTHON"; fi
    if [[ -n "${HERMES_VENV:-}" ]]; then printf '%s\n' "${HERMES_VENV}/bin/python3"; fi
    printf '%s\n' "${HOME}/.hermes/hermes-agent/venv/bin/python3"
    if command -v python3 >/dev/null 2>&1; then command -v python3; fi
    local v
    for v in 3.14 3.13 3.12 3.11 3.10 3.9; do
        if command -v "python${v}" >/dev/null 2>&1; then command -v "python${v}"; fi
    done
}

tried=""
while IFS= read -r py || [[ -n "$py" ]]; do
    [[ -n "$py" ]] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    case " ${tried} " in *" ${py} "*) continue ;; esac
    tried="${tried} ${py}"
    if "$py" -c 'import yaml' >/dev/null 2>&1; then
        exec "$py" "$gen" "$@"
    fi
done < <(candidates)

{
    echo "gen-skills-manifest: COULD NOT VERIFY - no interpreter with PyYAML found."
    echo "  Checked:${tried}"
    echo "  Fix one of:"
    echo "    - install PyYAML for your python3   (python3 -m pip install pyyaml)"
    echo "    - point this wrapper at one that has it:"
    echo "        PYTHON=/path/to/python3 bash $0"
} >&2
exit 3
