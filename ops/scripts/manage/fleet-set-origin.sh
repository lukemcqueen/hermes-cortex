#!/usr/bin/env bash
# fleet-set-origin.sh — repoint origin to the renamed repo.
#
# Idempotent: sets origin to the canonical URL only when it currently carries the
# legacy repo name; a host already on the new URL is a no-op. Does NOT pull or
# deploy (that belongs to UPDATE_REQUEST / cortex-update.sh) and never touches a
# host whose origin is something unexpected.
#
# Run via the agent-message-handler EXEC path (a deployed script in
# ~/.hermes-cortex/scripts/). Prints only to stdout; the EXEC_SUCCESS health path
# must not write stderr.
set -euo pipefail

REPO="${HOME}/hermes-cortex"
LEGACY="https://github.com/lukemcqueen/hermes-cortex.git"
CANONICAL="https://github.com/lukemcqueen/steadfaste-fleet.git"

if [ ! -d "${REPO}/.git" ]; then
  echo "fleet-set-origin: no git repo at ${REPO}"
  exit 1
fi

CUR="$(git -C "${REPO}" remote get-url origin 2>/dev/null || true)"

if [ -z "$CUR" ]; then
  git -C "${REPO}" remote add origin "$CANONICAL"
  echo "fleet-set-origin: no origin existed; set to ${CANONICAL}"
  exit 0
fi

case "$CUR" in
  "$CANONICAL")
    echo "fleet-set-origin: already ${CANONICAL} (no-op)"
    ;;
  "$LEGACY")
    git -C "${REPO}" remote set-url origin "$CANONICAL"
    echo "fleet-set-origin: origin ${LEGACY} -> ${CANONICAL}"
    ;;
  *)
    echo "fleet-set-origin: unexpected origin (${CUR}); leaving untouched"
    ;;
esac
