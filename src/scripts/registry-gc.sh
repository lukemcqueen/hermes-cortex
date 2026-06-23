#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  registry-gc.sh — Run garbage collection on registry cache
#
#  Prunes unused blob storage from the local Docker Hub cache,
#  freeing disk space. Safe to run while cache is in use.
#
#  Usage:
#    bash registry-gc.sh                    # dry-run (what would be deleted)
#    bash registry-gc.sh --apply            # actually delete
#    bash registry-gc.sh --report           # show disk usage before/after
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CONTAINER_NAME="${REGISTRY_CONTAINER:-registry-cache}"
CONFIG_FILE="/etc/docker/registry/config.yml"
DRY_RUN=true
REPORT=false

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) DRY_RUN=false; shift ;;
    --report) REPORT=true; shift ;;
    --help)
      echo "Usage: $(basename "$0") [--apply] [--report]"
      echo "  --apply   Actually delete unused blobs"
      echo "  --report  Show disk usage before/after"
      exit 0 ;;
    *) warn "Unknown: $1"; exit 1 ;;
  esac
done

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  warn "Container '${CONTAINER_NAME}' not running"
  exit 1
fi

# Disk usage before (if --report)
$REPORT && {
  echo "Before:"
  docker exec "$CONTAINER_NAME" du -sh /var/lib/registry 2>/dev/null || true
  echo ""
}

# Run GC
if $DRY_RUN; then
  info "Dry-run: would delete these unreferenced blobs:"
  docker exec "$CONTAINER_NAME" registry garbage-collect --dry-run "$CONFIG_FILE"
else
  info "Running garbage collection..."
  docker exec "$CONTAINER_NAME" registry garbage-collect "$CONFIG_FILE"
fi

# Disk usage after
$REPORT && {
  echo ""
  echo "After:"
  docker exec "$CONTAINER_NAME" du -sh /var/lib/registry 2>/dev/null || true
}

info "Done"
