#!/usr/bin/env bash
# require-fleet-venv.sh — the shared guard for EVERY fleet launcher that execs the venv.
#
# WHY A SHARED FILE. A launcher that bare-execs the fleet interpreter dies as bash's
# "line N: No such file or directory", which names neither the path nor the cause — and the
# same message covers causes that need different fixes:
#   1. the fleet venv was never created (nothing in this repo creates it);
#   2. the caller runs with a different $HOME, so a present path looks absent;
#   3. the payload (server script) was never deployed.
# loop-gov-mcp.sh taught this the expensive way on kustos (2026-10-13). Every launcher has
# the same wall, so the guard lives here once and they all source it.
#
# USAGE
#   source .../scripts/lib/require-fleet-venv.sh
#   require_fleet_venv "$PAYLOAD" [more payloads...]
#   exec "$(fleet_venv_python)" "$PAYLOAD" "$@"
#
# ENV
#   FLEET_VENV_DIR   override the venv root (tests use this; default ~/.hermes-cortex/venv)
#
# EXIT
#   78 (EX_CONFIG) from require_fleet_venv, after printing what is missing and how to fix it.

fleet_venv_dir() { printf '%s' "${FLEET_VENV_DIR:-${HOME}/.hermes-cortex/venv}"; }
fleet_venv_python() { printf '%s' "$(fleet_venv_dir)/bin/python3"; }

#: The repair sequence for an absent venv, in the order a human should run it.
fleet_venv_fix_hint() {
  echo "  create: python3 -m venv \"$(fleet_venv_dir)\""
  echo "  fill:   \"$(fleet_venv_python)\" \"${HOME}/.hermes-cortex/scripts/fix-cortex-venv.py\""
  echo "  (fixer not deployed yet? bash ~/hermes-cortex/ops/scripts/cortex-update.sh)"
}

require_fleet_venv() {
  local py; py="$(fleet_venv_python)"
  if [[ ! -x "$py" ]]; then
    echo "${0##*/}: NO INTERPRETER at $py" >&2
    echo "  HOME=${HOME}  (paths are relative to HOME; a different HOME in the caller is a cause)" >&2
    if [[ -e "$(fleet_venv_dir)" ]]; then
      echo "  the venv directory exists but has no usable bin/python3 (pruned? half-created?)" >&2
    else
      echo "  the fleet venv does not exist — nothing in this repo creates it" >&2
    fi
    fleet_venv_fix_hint >&2
    exit 78
  fi
  local payload
  for payload in "$@"; do
    [[ -f "$payload" ]] && continue
    echo "${0##*/}: NOT DEPLOYED at $payload" >&2
    echo "  HOME=${HOME}  (check this FIRST — a different HOME makes a present file look absent)" >&2
    echo "  deploy it: bash ~/hermes-cortex/ops/scripts/cortex-update.sh" >&2
    exit 78
  done
}
