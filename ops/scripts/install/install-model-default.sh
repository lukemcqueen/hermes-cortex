#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-model-default.sh
#
# Converges ~/.hermes/config.yaml model.default to the fleet's
# DEFAULT_MODEL convention so every NEW regular session (CLI or
# gateway) runs on the intended chat model — NOT the cron-only
# model.
#
# BACKGROUND (2026-08-18, Titus): ~/.hermes/config.yaml had
# model.default: deepseek-chat — the model deliberately pinned to
# LLM cron jobs — so every new regular session was about to run on
# the cron-only model. The intended convention was already encoded
# in ~/hermes-cortex/.env (DEFAULT_MODEL=deepseek-v4-flash);
# config.yaml simply disagreed with it. No migration or cron set
# the bad default — it was a stale manual setting. This installer
# makes config.yaml always follow the .env convention on every
# cortex-update, so a stale manual setting can never survive an
# update cycle again.
#
# CRON JOBS ARE INTENTIONALLY UNTOUCHED: LLM crons pin their model
# per-job (job.model wins in the scheduler — cron/scheduler.py
# run_job: per-job override > cron.model > HERMES_MODEL > model:
# config). This script only sets model.default; it never writes
# cron/jobs.json.
#
# Idempotent: silent no-op when the value already matches.
# Safe to run from cortex-update.sh on every update cycle.
# No restart needed — the gateway resolves model.default fresh per
# session (gateway/run.py _resolve_gateway_model).
# ───────────────────────────────────────────────────────────────
set -euo pipefail

HOME_DIR="${HOME:?}"
HERMES_HOME="${HERMES_HOME:-${HOME_DIR}/.hermes}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME_DIR}/.hermes-cortex}"

# ── Resolve the intended default model ────────────────────────
# Priority: runtime env > ~/hermes-cortex/.env (repo) >
# ~/.hermes-cortex/.env (deploy) > fleet fallback.
DEFAULT_MODEL="${DEFAULT_MODEL:-}"
if [[ -z "$DEFAULT_MODEL" && -f "${HOME_DIR}/hermes-cortex/.env" ]]; then
  DEFAULT_MODEL="$(grep -E '^DEFAULT_MODEL=' "${HOME_DIR}/hermes-cortex/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true)"
fi
if [[ -z "$DEFAULT_MODEL" && -f "${CORTEX_DEPLOY_HOME}/.env" ]]; then
  DEFAULT_MODEL="$(grep -E '^DEFAULT_MODEL=' "${CORTEX_DEPLOY_HOME}/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true)"
fi
DEFAULT_MODEL="${DEFAULT_MODEL:-deepseek-v4-flash}"

if [[ -z "$DEFAULT_MODEL" || "$DEFAULT_MODEL" == *" "* ]]; then
  echo "install-model-default: invalid DEFAULT_MODEL '${DEFAULT_MODEL}' — refusing to apply" >&2
  exit 1
fi

HERMES_CMD=""
for candidate in hermes "${HERMES_HOME}/hermes-agent/venv/bin/hermes"; do
  if command -v "$candidate" &>/dev/null; then
    HERMES_CMD="$candidate"
    break
  fi
done

if [[ -z "$HERMES_CMD" ]]; then
  echo "install-model-default: no hermes CLI found — skipped" >&2
  exit 0
fi

# ── Read current value ────────────────────────────────────────
CURRENT=""
CURRENT="$("$HERMES_CMD" config get model.default 2>/dev/null | tr -d '[:space:]' || true)"

if [[ "$CURRENT" == "$DEFAULT_MODEL" ]]; then
  echo "install-model-default: model.default already '${DEFAULT_MODEL}' — no change"
  exit 0
fi

echo "install-model-default: model.default '${CURRENT:-<unset>}' → '${DEFAULT_MODEL}'"

# ── Apply via hermes config set (canonical path, no hand-editing) ──
"$HERMES_CMD" config set model.default "$DEFAULT_MODEL" >/dev/null 2>&1 || true

# ── Verify what actually landed (read back from the file, not the tool) ──
APPLIED=""
if command -v python3 &>/dev/null; then
  APPLIED="$(python3 -c "
import yaml, sys
try:
    c = yaml.safe_load(open('${HERMES_HOME}/config.yaml'))
    m = c.get('model') or {}
    print(m.get('default', '') if isinstance(m, dict) else '')
except Exception:
    print('')
" 2>/dev/null || echo "")"
fi

if [[ "$APPLIED" == "$DEFAULT_MODEL" ]]; then
  echo "install-model-default: verified config.yaml model.default = ${APPLIED}"
else
  echo "install-model-default: WARNING — expected '${DEFAULT_MODEL}', read back '${APPLIED}'" >&2
  echo "  config.yaml may be managed elsewhere; check ${HERMES_HOME}/config.yaml model.default" >&2
  exit 1
fi
