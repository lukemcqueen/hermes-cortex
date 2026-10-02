#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# env-value.sh — print ONE provider secret for a consuming process.
#
# Usage:  env-value.sh OPENROUTER_API_KEY
#
# Why a script instead of telling a harness to source the env file:
#   sourcing `. ~/.hermes/.env` hands the caller the WHOLE environment, and a
#   coding agent can print its own environment (see the pi-coding-agent skill's
#   pitfall: "Hand pi only shell basics + the Jev/provider keys"). This extracts
#   exactly the ONE named variable and nothing else — no export, no source, no
#   leaked names. The caller decides where the value goes.
#
# Search order: the canonical cortex env first, then the Hermes-owned env (where
# provider keys currently live). First match wins, so a value added to the cortex
# env takes precedence without touching any consumer.
#
# Prints the VALUE only. Never prints the name or any other variable. Exit 1 with
# a message on stderr when the name is absent — a consumer must fail closed, not
# run with an empty credential.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

name="${1:-}"
if [[ -z "$name" ]]; then
  echo "usage: env-value.sh <VAR_NAME>" >&2
  exit 2
fi
# Validate before using it in a pattern: an injected name must not become a regex
# or reach outside the intended files.
if [[ ! "$name" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
  echo "env-value: invalid variable name" >&2
  exit 2
fi

for f in "${CORTEX_ENV_FILE:-$HOME/hermes-cortex/.env}" "$HOME/.hermes/.env"; do
  [[ -f "$f" ]] || continue
  line="$(grep -m1 "^${name}=" "$f" 2>/dev/null || true)"
  [[ -n "$line" ]] || continue
  v="${line#*=}"
  # strip one layer of surrounding quotes, in either style
  v="${v%\"}"; v="${v#\"}"
  v="${v%\'}"; v="${v#\'}"
  printf '%s' "$v"
  exit 0
done

echo "env-value: $name not found in the cortex env or the Hermes env" >&2
exit 1
