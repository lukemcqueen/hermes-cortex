#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  setup-registry-cache.sh — Deploy Docker Hub pull-through cache
#
#  Deploys registry:3 as a pull-through proxy for Docker Hub.
#  Run on the machine that will host the cache (typically Moses).
#
#  After deployment, configure every client machine's daemon.json:
#    { "registry-mirrors": ["http://cache-host:5000"] }
#
#  Usage:
#    bash setup-registry-cache.sh                    # deploy with defaults
#    bash setup-registry-cache.sh --port 5000        # custom port
#    bash setup-registry-cache.sh --compose-file     # print docker-compose only
#    bash setup-registry-cache.sh --help             # full help
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../../deploy/docker-compose.registry.yml"

PORT="${REGISTRY_PORT:-5000}"
CACHE_DIR="${REGISTRY_CACHE_DIR:-/data/registry-cache}"
DRY_RUN=false

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error() { printf "${RED}✗${RESET} %s\n" "$*"; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy Docker Hub pull-through cache using registry:3.

Options:
  --port PORT       Listen port (default: 5000, env: REGISTRY_PORT)
  --dir PATH        Cache storage directory (default: /data/registry-cache)
  --compose-file    Print the docker-compose config and exit
  --dry-run         Show what would be done without deploying
  --help            Show this message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --dir) CACHE_DIR="$2"; shift 2 ;;
    --compose-file) cat "$COMPOSE_FILE"; exit 0 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) usage ;;
    *) warn "Unknown option: $1"; usage ;;
  esac
done

header() {
  printf "\n${CYAN}━━━ %s ━━━${RESET}\n" "$1"
}

# ── Pre-flight ───────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  error "Docker not found"
  exit 1
fi

# ── Deploy ───────────────────────────────────────────────────
header "Registry Cache Deployment"

if $DRY_RUN; then
  info "[DRY-RUN] Would deploy registry:3 on port ${PORT}"
  info "[DRY-RUN] Cache volume: ${CACHE_DIR}"
  info "Run without --dry-run to deploy"
  exit 0
fi

# Pull the image
echo "Pulling registry:3..."
docker pull registry:3

# Create cache directory
mkdir -p "$CACHE_DIR"

# Deploy container
echo "Starting registry-cache on port ${PORT}..."
docker rm -f registry-cache 2>/dev/null || true
docker run -d --restart always --name registry-cache \
  -p "${PORT}:5000" \
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  -v "${CACHE_DIR}:/var/lib/registry" \
  registry:3

echo ""
info "Registry cache deployed"
echo "  Port:  ${PORT}"
echo "  Cache: ${CACHE_DIR}"
echo ""

# ── Client config instructions ───────────────────────────────
header "Client Configuration"

cat <<CLIENT_CONFIG
On every machine that should use this cache:

1. Edit daemon.json:
   Linux:   /etc/docker/daemon.json
   macOS:   ~/.docker/daemon.json
   colima:  colima ssh → sudo vi /etc/docker/daemon.json

   Add:
   {
     "registry-mirrors": ["http://$(hostname):${PORT}"]
   }

2. Restart Docker:
   Linux:   sudo systemctl restart docker
   macOS:   Docker Desktop → Settings → Apply & Restart
   colima:  colima restart

3. Verify:
   docker pull alpine:latest
   docker logs registry-cache  # should show proxied request

4. (Optional) BuildKit config for docker build:
   Create /etc/buildkitd.toml:
     [registry."docker.io"]
       mirrors = ["http://$(hostname):${PORT}"]

   Then create builder:
     docker buildx create --use --bootstrap \
       --name cache-builder \
       --driver docker-container \
       --buildkitd-config /etc/buildkitd.toml

CLIENT_CONFIG

# ── GC cron suggestion ───────────────────────────────────────
header "Periodic Garbage Collection"

cat <<GC
Add this cron to run monthly GC:
  0 3 1 * * docker exec registry-cache registry garbage-collect /etc/docker/registry/config.yml

Or use the automated helper:
  bash ~/.hermes/scripts/registry-gc.sh

GC
