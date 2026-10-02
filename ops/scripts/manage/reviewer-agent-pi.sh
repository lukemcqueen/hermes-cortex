#!/usr/bin/env bash
# reviewer-agent-pi.sh — Read-only adversarial-review backend using the pi coding
# agent (moonshotai/kimi-k2.6 via OpenRouter by default; override with
# REVIEWER_PI_MODEL).
#
# Pluggable adversarial reviewer "agent" backend: the close-gate shells out to
# this command with the review prompt on STDIN and reads findings JSON from
# stdout. Read-only is enforced HERE (the gate cannot revoke what the command
# allows) so the reviewer can inspect/verify but never edit the tree — a
# reviewer that can write can fix its own objections. Fail-closed upsteam: a
# non-zero exit or empty output is refused by the gate.
#
# Requires: pi CLI installed, and an OpenRouter credential (OPENROUTER_API_KEY,
# or sourced from ~/.hermes/.env). Configure the gate with:
#   ADVERSARIAL_REVIEW_BACKEND=agent
#   ADVERSARIAL_REVIEW_AGENT_CMD=<this script>
#   ADVERSARIAL_REVIEW_AGENT_NAME=pi
set -euo pipefail

MODEL="${REVIEWER_PI_MODEL:-openrouter/moonshotai/kimi-k2.6}"

# pi needs the OpenRouter credential to reach the model.
if [[ -z "${OPENROUTER_API_KEY:-}" && -f "${HOME}/.hermes/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^OPENROUTER_API_KEY=' "${HOME}/.hermes/.env")
  set +a
fi
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "reviewer-agent-pi: OPENROUTER_API_KEY is not set" >&2
  exit 3
fi

# Read the review prompt from stdin.
PROMPT="$(cat)"

exec pi --model "${MODEL}" \
  --tools read \
  "You are an independent, adversarial, read-only code reviewer. You may open and
read the repo, run tests and check claims, but you may NOT edit, write, or fix
anything. Given the review material, produce your findings as JSON on stdout with
keys: verdict, findings[]. Be strict. Material follows:
${PROMPT}"
