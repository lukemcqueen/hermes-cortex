#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-provider-timeouts.sh
#
# Sets per-provider request timeouts in ~/.hermes/config.yaml so a
# silently-hanging provider API call becomes a real ReadTimeout error
# — letting the retry/fallback chain engage BEFORE the scheduler's
# inactivity watchdog (HERMES_CRON_TIMEOUT) kills the job.
#
# BACKGROUND (fleet-wide LLM-cron hang class, diagnosed on Gisu's
# host 2026-08-06): deepseek's non-streaming endpoint intermittently
# hangs (no response, no error, no stream deltas) for >10 minutes.
# Three LLM crons at 09:00 hit the same hang; the watchdog killed one
# at 600s idle, two stuck in 'running'. The config.yaml fallback chain
# (opencode-zen, ollama-local) NEVER engages because a silent hang
# raises no exception — fallback only fires on raised errors. The fix:
# a per-request timeout so the hang becomes ReadTimeout at 5 min,
# before the 600s watchdog.
#
# ORTHOGONAL to HERMES_CRON_TIMEOUT: do NOT touch the watchdog — the
# 30s/300s experiments broke 9/9 evening runs; 600s is known-good.
# This is per-request, applied via `hermes config set`.
#
# Idempotent: silent no-op when the value already matches.
# Safe to run from cortex-update.sh on every update cycle.
# No restart needed — config.yaml is read per-request.
# ───────────────────────────────────────────────────────────────
set -euo pipefail

HOME_DIR="${HOME:?}"
HERMES_HOME="${HERMES_HOME:-${HOME_DIR}/.hermes}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME_DIR}/.hermes-cortex}"
STATE_FILE="${CORTEX_DEPLOY_HOME}/state/provider-timeouts"

# Values (override per machine via ~/hermes-cortex/.env)
REQUEST_TIMEOUT="${DEEPSEEK_REQUEST_TIMEOUT:-300}"
STALE_TIMEOUT="${DEEPSEEK_STALE_TIMEOUT:-300}"

# Validate numeric
for v in "$REQUEST_TIMEOUT" "$STALE_TIMEOUT"; do
  case "$v" in
    ''|*[!0-9]*)
      echo "install-provider-timeouts: invalid timeout '$v' (must be numeric seconds)" >&2
      exit 1
      ;;
  esac
done

HERMES_CMD=""
for candidate in hermes "${HERMES_HOME}/hermes-agent/venv/bin/hermes"; do
  if command -v "$candidate" &>/dev/null; then
    HERMES_CMD="$candidate"
    break
  fi
done

if [[ -z "$HERMES_CMD" ]]; then
  echo "install-provider-timeouts: no hermes CLI found — skipped" >&2
  exit 0
fi

# ── Apply via hermes config set (nested key support confirmed) ──
"$HERMES_CMD" config set providers.deepseek.request_timeout_seconds "$REQUEST_TIMEOUT" >/dev/null 2>&1 || true
"$HERMES_CMD" config set providers.deepseek.stale_timeout_seconds "$STALE_TIMEOUT" >/dev/null 2>&1 || true

# ── Verify what actually landed ────────────────────────────────
APPLIED_REQ=""
APPLIED_STALE=""
if command -v python3 &>/dev/null; then
  read -r APPLIED_REQ APPLIED_STALE < <(python3 -c "
import yaml, sys
try:
    c = yaml.safe_load(open('${HERMES_HOME}/config.yaml'))
    d = (c.get('providers') or {}).get('deepseek') or {}
    print(d.get('request_timeout_seconds', ''), d.get('stale_timeout_seconds', ''))
except Exception:
    print('', '')
" 2>/dev/null || echo "")
fi

if [[ "$APPLIED_REQ" == "$REQUEST_TIMEOUT" && "$APPLIED_STALE" == "$STALE_TIMEOUT" ]]; then
  mkdir -p "$(dirname "$STATE_FILE")"
  printf '%s:%s\n' "$REQUEST_TIMEOUT" "$STALE_TIMEOUT" > "$STATE_FILE"
  echo "providers.deepseek request/stale timeout = ${REQUEST_TIMEOUT}/${STALE_TIMEOUT}s applied"
else
  echo "install-provider-timeouts: WARNING — expected ${REQUEST_TIMEOUT}/${STALE_TIMEOUT}s, read back ${APPLIED_REQ}/${APPLIED_STALE}s" >&2
  echo "  config.yaml may be managed elsewhere; check ${HERMES_HOME}/config.yaml providers.deepseek" >&2
fi
