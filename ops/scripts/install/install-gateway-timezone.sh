#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-gateway-timezone.sh
#
# Ensures HERMES_TIMEZONE (IANA name, e.g. Asia/Seoul) is applied to
# the Hermes gateway process so that EVERY cron script it spawns
# inherits the configured timezone. Without this, cron scripts fall
# back to system local time — which is correct today (all fleet hosts
# are Asia/Seoul) but breaks the "env var is the source of truth"
# contract the moment a host's system TZ differs from HERMES_TIMEZONE.
#
#   Linux  → systemd user drop-in on hermes-gateway.service
#            (survives unit regeneration; never touches ~/.hermes/.env)
#   macOS  → idempotent append to ~/.hermes/.env (launchd gateway —
#            Hermes loads it at start; the cron-timeout pattern)
#
# Value: ${HERMES_TIMEZONE:-Asia/Seoul} — override per machine via
# ~/hermes-cortex/.env (sourced by cortex-update.sh before this runs).
#
# ⚠️  Activation requires a gateway restart (same contract as
#     install-gateway-cron-timeout.sh): systemd drop-ins are read at
#     process exec. This script deliberately does NOT restart — the
#     gateway lifecycle guard scans scripts for restart patterns.
#     Until the next `hermes update` / operator restart, scripts that
#     use hermes_tz.py fall back to system local time (which matches
#     HERMES_TIMEZONE on every current fleet host, so no visible gap).
#
# Idempotent: silent no-op when the applied value already matches.
# Safe to run from cortex-update.sh on every update cycle.
# ───────────────────────────────────────────────────────────────
set -euo pipefail

VALUE="${HERMES_TIMEZONE:-Asia/Seoul}"
case "$VALUE" in
  ''|*[!A-Za-z0-9_/+-]*)
    echo "install-gateway-timezone: invalid HERMES_TIMEZONE='${VALUE}' (must be an IANA name like Asia/Seoul)" >&2
    exit 1
    ;;
esac

HOME_DIR="${HOME:?}"
HERMES_HOME="${HERMES_HOME:-${HOME_DIR}/.hermes}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME_DIR}/.hermes-cortex}"
STATE_FILE="${CORTEX_DEPLOY_HOME}/state/gateway-timezone-env"

MECH=""

if [[ -f "${HOME_DIR}/.config/systemd/user/hermes-gateway.service" ]] && command -v systemctl >/dev/null 2>&1; then
  # ── Linux: systemd user drop-in ─────────────────────────────
  UNIT_DIR="${HOME_DIR}/.config/systemd/user/hermes-gateway.service.d"
  mkdir -p "${UNIT_DIR}"
  cat > "${UNIT_DIR}/11-timezone.conf" <<EOF
# Managed by install-gateway-timezone.sh (cortex-update.sh)
# IANA timezone for cron runtime (HERMES_TIMEZONE). All cron scripts
# and hermes_tz.py derive displayed timezone from this env var.
[Service]
Environment="HERMES_TIMEZONE=${VALUE}"
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
    grep -q '^HERMES_TIMEZONE=' "${ENV_FILE}" && sed -i '' '/^HERMES_TIMEZONE=/d' "${ENV_FILE}"
    printf '\n# IANA timezone for cron runtime (managed by install-gateway-timezone.sh)\nHERMES_TIMEZONE=%s\n' "${VALUE}" >> "${ENV_FILE}"
  fi
  MECH="macos-env"
else
  echo "install-gateway-timezone: no gateway service manager found — skipped"
  exit 0
fi

mkdir -p "$(dirname "${STATE_FILE}")"
LAST="$(cat "${STATE_FILE}" 2>/dev/null || echo "")"
if [[ "${LAST}" != "${VALUE}:${MECH}" ]]; then
  printf '%s:%s\n' "${VALUE}" "${MECH}" > "${STATE_FILE}"
  echo "HERMES_TIMEZONE=${VALUE} applied (${MECH})"
  echo "RESTART PENDING: gateway restart required to activate (next hermes update or operator restart)"
else
  echo "HERMES_TIMEZONE=${VALUE} already applied (${MECH})"
fi
