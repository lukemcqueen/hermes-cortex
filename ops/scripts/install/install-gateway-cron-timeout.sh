#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-gateway-cron-timeout.sh
#
# Ensures HERMES_CRON_TIMEOUT (LLM cron inactivity timeout, seconds)
# is applied to the Hermes gateway process. The scheduler inside the
# gateway uses this env var to kill cron jobs that go idle — the
# upstream default is 600s, which tolerates a hung provider API call
# for ten minutes before the cron is killed as a TimeoutError.
# Fleet default here: 30s — a provider stall is detected in half a
# minute instead of hanging a cron for ten.
#
#   Linux  → systemd user drop-in on hermes-gateway.service
#            (survives unit regeneration; never touches ~/.hermes/.env)
#   macOS  → idempotent append to ~/.hermes/.env (launchd gateway —
#            the langfuse-fleet-script pattern; Hermes loads it at start)
#
# Value: ${HERMES_CRON_TIMEOUT:-30} — override per machine via
# ~/hermes-cortex/.env (sourced by cortex-update.sh before this runs).
# 0 = unlimited.
#
# ⚠️  Activation requires a gateway restart: systemd drop-ins are read
#     at process exec, so this script intentionally does NOT issue a
#     restart command — the gateway lifecycle guard scans cron scripts
#     AND every script they reference for gateway restart patterns,
#     and cortex-update.sh runs from inside the gateway (agent cron).
#     The gateway restarts routinely via `hermes update` or operator
#     restart; this script prints RESTART PENDING when one is needed.
#
# Idempotent: silent no-op when the applied value already matches.
# Safe to run from cortex-update.sh on every update cycle.
# ───────────────────────────────────────────────────────────────
set -euo pipefail

VALUE="${HERMES_CRON_TIMEOUT:-30}"
case "$VALUE" in
  ''|*[!0-9]*)
    echo "install-gateway-cron-timeout: invalid HERMES_CRON_TIMEOUT='${VALUE}' (must be numeric seconds; 0 = unlimited)" >&2
    exit 1
    ;;
esac

HOME_DIR="${HOME:?}"
HERMES_HOME="${HERMES_HOME:-${HOME_DIR}/.hermes}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME_DIR}/.hermes-cortex}"
STATE_FILE="${CORTEX_DEPLOY_HOME}/state/cron-timeout-env"

MECH=""

if [[ -f "${HOME_DIR}/.config/systemd/user/hermes-gateway.service" ]] && command -v systemctl >/dev/null 2>&1; then
  # ── Linux: systemd user drop-in ─────────────────────────────
  UNIT_DIR="${HOME_DIR}/.config/systemd/user/hermes-gateway.service.d"
  mkdir -p "${UNIT_DIR}"
  cat > "${UNIT_DIR}/10-cron-timeout.conf" <<EOF
# Managed by install-gateway-cron-timeout.sh (cortex-update.sh)
# LLM cron inactivity timeout in seconds. 0 = unlimited.
[Service]
Environment="HERMES_CRON_TIMEOUT=${VALUE}"
EOF
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  MECH="systemd"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  # ── macOS: launchd gateway — idempotent append to ~/.hermes/.env ──
  ENV_FILE="${HERMES_HOME}/.env"
  if [[ ! -f "${ENV_FILE}" ]]; then
    touch "${ENV_FILE}" 2>/dev/null || true
  fi
  if [[ -f "${ENV_FILE}" ]]; then
    grep -q '^HERMES_CRON_TIMEOUT=' "${ENV_FILE}" && sed -i '' '/^HERMES_CRON_TIMEOUT=/d' "${ENV_FILE}"
    printf '\n# LLM cron inactivity timeout (managed by install-gateway-cron-timeout.sh)\nHERMES_CRON_TIMEOUT=%s\n' "${VALUE}" >> "${ENV_FILE}"
  fi
  MECH="macos-env"
else
  echo "install-gateway-cron-timeout: no gateway service manager found — skipped"
  exit 0
fi

mkdir -p "$(dirname "${STATE_FILE}")"
LAST="$(cat "${STATE_FILE}" 2>/dev/null || echo "")"
if [[ "${LAST}" != "${VALUE}:${MECH}" ]]; then
  printf '%s:%s\n' "${VALUE}" "${MECH}" > "${STATE_FILE}"
  echo "HERMES_CRON_TIMEOUT=${VALUE} applied (${MECH})"
  echo "RESTART PENDING: gateway restart required to activate (next hermes update or operator restart)"
else
  echo "HERMES_CRON_TIMEOUT=${VALUE} already applied (${MECH})"
fi
