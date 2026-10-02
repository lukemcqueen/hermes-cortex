#!/usr/bin/env bash
# env-secret.sh — print EXACTLY ONE named variable and nothing else.
#
# Designed for the pi-coding-agent provider config: a harness needs ONE secret
# (e.g. OPENROUTER_API_KEY) but must never be handed the whole environment.
# Sourcing ~/.hermes/.env gives a coding agent EVERY secret in it (its bash tool
# can print any env var it was given) — so this script resolves a single named
# variable and prints only its value.
#
# Behavior (fixed, fail-closed):
#   - searches the cortex env (~/hermes-cortex/.env, then the deploy root) first,
#     then the Hermes env (~/.hermes/.env) — first match wins, so a value added
#     to the cortex env takes precedence with no consumer change;
#   - prints the VALUE only — no export, no source, no other names;
#   - absent name -> exit 1 with a stderr message (a consumer never runs with an
#     empty credential);
#   - validates the name against ^[A-Z][A-Z0-9_]*$ BEFORE using it in a pattern,
#     so an injected name cannot become a regex or reach outside the intended
#     files (bad name -> exit 2).
#
# Usage: env-secret.sh VARNAME
set -euo pipefail

name="${1:-}"
if [[ -z "$name" ]]; then
  echo "env-secret: no variable name given" >&2
  exit 2
fi

# Validate BEFORE any pattern use (fail-closed against injected names).
if ! printf '%s' "$name" | grep -qE '^[A-Z][A-Z0-9_]*$'; then
  echo "env-secret: invalid variable name '$name'" >&2
  exit 2
fi

# Candidate env files, MOST canonical first (matches loop-gov-mcp env order).
candidates=()
for d in "${CORTEX_REPO:-$HOME/hermes-cortex}" "$HOME/hermes-cortex" "$HOME/.hermes-cortex"; do
  if [[ -f "$d/.env" ]]; then
    candidates+=("$d/.env")
  fi
done
candidates+=("$HOME/.hermes/.env")

# Regex built from the validated name (safe — name is ^[A-Z][A-Z0-9_]*$).
re="^${name}="
for f in "${candidates[@]}"; do
  [[ -f "$f" ]] || continue
  # Read only the line(s) naming our variable; strip double or single quotes.
  while IFS= read -r line; do
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    if [[ "$line" == "$name="* ]]; then
      val="${line#*=}"
      val="${val%\"}"    # strip trailing quote
      val="${val#\"}"    # strip leading quote
      val="${val%\'}"
      val="${val#\'}"
      printf '%s\n' "$val"
      exit 0
    fi
  done < <(grep -E "$re" "$f" 2>/dev/null || true)
done

echo "env-secret: '$name' not found in any env file" >&2
exit 1
