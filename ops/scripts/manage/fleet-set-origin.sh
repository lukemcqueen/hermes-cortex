#!/usr/bin/env bash
# fleet-set-origin.sh — repoint origin to the renamed repo.
#
# Idempotent: sets origin to the canonical URL only when it currently carries the
# legacy repo name; a host already on the new URL is a no-op. Does NOT pull or
# deploy (that belongs to UPDATE_REQUEST / fleet-update.sh) and never touches a
# host whose origin is something unexpected.
#
# Run via the agent-message-handler EXEC path (a deployed script in
# ~/.hermes-cortex/scripts/). Prints only to stdout on the SUCCESS paths; git may
# write its own stderr on a failure, which this script propagates with exit!=0.
set -euo pipefail

# Env-overridable so a test can point it at throwaway git repos.
REPO="${FLEET_SET_ORIGIN_REPO:-${HOME}/hermes-cortex}"
LEGACY="https://github.com/lukemcqueen/hermes-cortex.git"
CANONICAL="https://github.com/lukemcqueen/steadfaste-fleet.git"

if [ ! -d "${REPO}/.git" ]; then
  echo "fleet-set-origin: no git repo at ${REPO}"
  exit 1
fi

# Distinguish "no origin configured" (git config rc 1) from a real git failure
# (any other non-zero rc): only a real failure is fatal; no-origin is a state.
set +e
_origin_out="$(git -C "${REPO}" config --get remote.origin.url 2>&1)"
_origin_rc=$?
set -e
if [ "$_origin_rc" -ne 0 ] && [ "$_origin_rc" -ne 1 ]; then
  echo "fleet-set-origin: could not read origin (rc=$_origin_rc): $_origin_out"
  exit 1
fi
CUR="$_origin_out"

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
