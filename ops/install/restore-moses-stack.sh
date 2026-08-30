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
# Compose reads ${MYCORTEX_PG_PASSWORD} from ITS project .env
# (~/.hermes-cortex/.env), NOT the repo .env (single source of truth).
# Provision the deploy-home .env with the value from the repo .env.
log "provisioning ~/.hermes-cortex/.env (MYCORTEX_PG_PASSWORD for compose)"
DEPLOY_ENV="${DEPLOY}/.env"
if grep -q '^MYCORTEX_PG_PASSWORD=' "${DEPLOY_ENV}" 2>/dev/null; then
  log "MYCORTEX_PG_PASSWORD already in deploy .env"
elif [[ -f "${REPO}/.env" ]] && grep -q '^MYCORTEX_PG_PASSWORD=' "${REPO}/.env"; then
  grep '^MYCORTEX_PG_PASSWORD=' "${REPO}/.env" >> "${DEPLOY_ENV}"
  chmod 600 "${DEPLOY_ENV}"
  log "copied MYCORTEX_PG_PASSWORD from repo .env"
else
  log "generating fresh MYCORTEX_PG_PASSWORD"
  echo "MYCORTEX_PG_PASSWORD=$(openssl rand -hex 20)" >> "${DEPLOY_ENV}"
  chmod 600 "${DEPLOY_ENV}"
fi

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

# 4. Immutable enforcement layer (hermes-plugin-lock targets: enforcer, hooks)
if command -v hermes-plugin-lock >/dev/null 2>&1; then
  log "applying immutable layer (hermes-plugin-lock lock)"
  hermes-plugin-lock lock && log "enforcement files immutable" \
    || warn "hermes-plugin-lock lock failed — check sudoers entry"
elif [[ -x "${DEPLOY}/scripts/hermes-plugin-lock" ]]; then
  log "applying immutable layer (deployed hermes-plugin-lock lock)"
  bash "${DEPLOY}/scripts/hermes-plugin-lock" lock \
    && log "enforcement files immutable" \
    || warn "hermes-plugin-lock lock failed — check sudoers entry"
else
  warn "hermes-plugin-lock not found — immutable layer not applied"
fi

# 5. Ollama (models needed for scoring/embeddings; pull if empty)
if systemctl is-active ollama >/dev/null 2>&1; then
  log "ollama already running"
else
  log "starting ollama"
  systemctl enable --now ollama 2>/dev/null || systemctl start ollama || warn "ollama failed to start"
fi
sleep 2
if curl -s -m 5 http://localhost:11434/api/tags >/dev/null 2>&1; then
  EMB_MODEL=$(grep -E '^EMBEDDING_MODEL=' "${REPO}/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "nomic-embed-text:v1.5")
  if curl -s -m 5 http://localhost:11434/api/tags | grep -q "${EMB_MODEL}"; then
    log "embedding model ${EMB_MODEL} present"
  else
    log "pulling ${EMB_MODEL} (first run — may take minutes)"
    ollama pull "${EMB_MODEL}" 2>&1 | tail -1 || warn "pull failed — run: ollama pull ${EMB_MODEL}"
  fi
else
  warn "ollama still not responding after start — check service"
fi

log "done. Next (as moses): bash ~/.hermes-cortex/scripts/cortex-update.sh 2>&1 | tail -30"