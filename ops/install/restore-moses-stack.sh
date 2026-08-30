#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# restore-moses-stack.sh — post-migration stack bring-up (moses host)
# Run once with:  sudo bash ~/hermes-cortex/ops/install/restore-moses-stack.sh
# Idempotent. 2026-08-30. Covers the root-needing steps only;
# the rest of the deploy (cortex-update.sh) runs as the moses user.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

HOME_MOSES="/home/moses"
DEPLOY="${HOME_MOSES}/.hermes-cortex"
REPO="${HOME_MOSES}/hermes-cortex"

log() { printf '✓ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "run as root: sudo bash $0"

# 1. Docker daemon + moses group membership
log "starting docker"
systemctl enable --now docker 2>/dev/null || systemctl start docker
systemctl is-active docker >/dev/null || die "docker failed to start"

if ! id -nG moses | tr ' ' '\n' | grep -qx docker; then
  log "adding moses to docker group"
  usermod -aG docker moses
  warn "moses must log out/in (or 'newgrp docker') before group takes effect"
fi

# 2. mycortex-postgres compose
log "bringing up mycortex-postgres (:15432)"
if ! docker ps --format '{{.Names}}' | grep -q '^mycortex-postgres$'; then
  (cd "${DEPLOY}" && docker compose -f docker-compose.mycortex.yml up -d)
else
  log "mycortex-postgres already running"
fi

# 3. nginx service configs (hermes-services.conf + orch + zone-defs)
if [[ -x "${DEPLOY}/scripts/install-nginx.sh" ]]; then
  log "deploying nginx configs (install-nginx.sh)"
  bash "${DEPLOY}/scripts/install-nginx.sh" || warn "install-nginx.sh exited non-zero — check output"
else
  warn "install-nginx.sh not deployed — run cortex-update first, then re-run this"
fi

nginx -t 2>/dev/null && nginx -s reload 2>/dev/null && log "nginx reloaded" || warn "nginx -t failed — fix configs before reload"

log "done. Next (as moses): bash ~/.hermes-cortex/scripts/cortex-update.sh 2>&1 | tail -30"