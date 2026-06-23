#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  setup-registry-cache.sh — Deploy Docker Hub pull-through cache
#
#  Deploys registry:3 as a pull-through proxy. Supports chaining:
#    Titus → Joseph → Docker Hub
#    Gisu  → Docker Hub
#
#  Usage:
#    bash setup-registry-cache.sh \
#      --name registry \
#      --port 5000 \
#      [--upstream http://joseph:5000] \
#      [--dir /data/registry]
#
#  Examples:
#    # Joseph/Gisu: direct to Docker Hub
#    bash setup-registry-cache.sh --port 5000 --dir /data/registry
#
#    # Titus: chain to Joseph
#    bash setup-registry-cache.sh \
#      --port 5000 --dir ~/docker/cache \
#      --upstream http://joseph:5000
#
#    # Print docker-compose for your config:
#    bash setup-registry-cache.sh --compose-file [--upstream http://joseph:5000]
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../../deploy/docker-compose.registry.yml"

NAME="${REGISTRY_NAME:-registry}"
PORT="${REGISTRY_PORT:-5000}"
CACHE_DIR="${REGISTRY_CACHE_DIR:-/data/registry}"
UPSTREAM="${REGISTRY_UPSTREAM:-}"
DRY_RUN=false
SHOW_COMPOSE=false

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy Docker Hub pull-through cache using registry:3.

Options:
  --name NAME       Container/compose name (default: registry)
  --port PORT       Listen port (default: 5000, env: REGISTRY_PORT)
  --dir PATH        Cache storage directory (default: /data/registry)
  --upstream URL    Parent cache to proxy through (e.g. http://joseph:5000)
                    Default: direct to Docker Hub
  --compose-file    Print the docker-compose config for your args and exit
  --dry-run         Show what would be done without deploying
  --help            Show this message

Examples:
  # Joseph: direct to Docker Hub
  $(basename "$0") --port 5000 --dir /data/registry

  # Titus: chain to Joseph
  $(basename "$0") --port 5000 --dir ~/docker/cache --upstream http://joseph:5000

  # Print compose config
  $(basename "$0") --compose-file --upstream http://joseph:5000
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --dir) CACHE_DIR="$2"; shift 2 ;;
    --upstream) UPSTREAM="$2"; shift 2 ;;
    --compose-file) SHOW_COMPOSE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) usage ;;
    *) warn "Unknown option: $1"; usage ;;
  esac
done

# Determine the remote URL for REGISTRY_PROXY_REMOTEURL
if [[ -n "$UPSTREAM" ]]; then
  REMOTE_URL="$UPSTREAM"
  CHAIN_LABEL="→ ${UPSTREAM}"
else
  REMOTE_URL="https://registry-1.docker.io"
  CHAIN_LABEL="→ Docker Hub"
fi

# Prevent Titus from accidentally being reachable from LAN
if [[ "$PORT" == "127.0.0.1:"* ]]; then
  BIND="$PORT"
elif [[ "$NAME" == "titus"* || "$(hostname)" == "titus"* ]]; then
  BIND="127.0.0.1:${PORT}"
else
  BIND="0.0.0.0:${PORT}"
fi

# ── Print compose file ───────────────────────────────────────
if $SHOW_COMPOSE; then
  cat <<YAML
# Registry cache: ${NAME} ${CHAIN_LABEL}
# Deploy: UPSTREAM="${REMOTE_URL}" REGISTRY_PORT="${BIND}" docker compose -f ${COMPOSE_FILE} up -d
services:
  ${NAME}:
    image: registry:3
    restart: always
    ports:
      - "${BIND}:5000"
    environment:
      REGISTRY_PROXY_REMOTEURL: "${REMOTE_URL}"
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - ${NAME}-data:/var/lib/registry
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:5000/v2/"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  ${NAME}-data:
YAML
  exit 0
fi

# ── Pre-flight ───────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "Error: Docker not found"
  exit 1
fi

# ── Deploy ───────────────────────────────────────────────────
echo ""
printf "${CYAN}━━━ Registry Cache: ${NAME} ${CHAIN_LABEL} ━━━${RESET}\n\n"

if $DRY_RUN; then
  info "[DRY-RUN] Would deploy:"
  echo "  Container: ${NAME}"
  echo "  Port:      ${BIND}"
  echo "  Cache:     ${CACHE_DIR}"
  echo "  Upstream:  ${REMOTE_URL}"
  echo ""
  echo "  Run without --dry-run to deploy"
  exit 0
fi

# Pull the image
echo "Pulling registry:3..."
docker pull registry:3

# Create cache directory
mkdir -p "$CACHE_DIR"

# Remove existing container with same name
docker rm -f "${NAME}" 2>/dev/null || true

# Deploy
echo "Starting ${NAME} on port ${BIND}..."
docker run -d --restart always --name "${NAME}" \
  -p "${BIND}:5000" \
  -e REGISTRY_PROXY_REMOTEURL="${REMOTE_URL}" \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  -v "${CACHE_DIR}:/var/lib/registry" \
  registry:3

echo ""
info "${NAME} deployed"
echo "  Port:     ${BIND}"
echo "  Cache:    ${CACHE_DIR}"
echo "  Upstream: ${REMOTE_URL}"
echo ""

# ── Client config ────────────────────────────────────────────
HOSTNAME="$(hostname 2>/dev/null || echo 'localhost')"
MIRROR_URL="http://${HOSTNAME}:${PORT}"

printf "${CYAN}━━━ Client daemon.json ━━━${RESET}\n\n"
echo "On machines that should use this cache, add to daemon.json:"
echo ""
echo "  {"
echo "    \"registry-mirrors\": [\"${MIRROR_URL}\"]"
echo "  }"
echo ""
echo "For chained config (e.g., Titus → Joseph):"
echo "  {"
echo "    \"registry-mirrors\": ["
echo "      \"http://localhost:5000\","
echo "      \"http://joseph:5000\""
echo "    ]"
echo "  }"
echo ""

printf "${CYAN}━━━ BuildKit Config (optional) ━━━${RESET}\n\n"
echo "For docker build support, create /etc/buildkitd.toml:"
echo "  [registry.\"docker.io\"]"
echo "    mirrors = [\"${MIRROR_URL}\"]"
echo ""
echo "Then: docker buildx create --use --bootstrap --name cache-builder \\"
echo "  --driver docker-container \\"
echo "  --buildkitd-config /etc/buildkitd.toml"
echo ""

printf "${CYAN}━━━ Monthly GC ━━━${RESET}\n\n"
echo "Add to cron:"
echo "  0 3 1 * * docker exec ${NAME} registry garbage-collect /etc/docker/registry/config.yml"
echo "Or: bash ~/.hermes/scripts/registry-gc.sh --apply --report"
echo ""
