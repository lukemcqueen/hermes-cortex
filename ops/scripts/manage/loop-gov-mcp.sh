#!/usr/bin/env bash
# Wrapper for loop-gov-mcp.py — uses dedicated venv with mcp package
# P1-A hardening (2026-07-31): exec the IMMUTABLE deployed copy
# (~/.hermes-cortex/tools/loop-governance/), NOT the user-writable repo
# working tree. Editing the repo copy must not disable begin_change
# enforcement. The deployed copy is kept current by cortex-update.sh
# (register entry) and locked by hermes-plugin-lock.
#
# The MISSING-PATH diagnosis is SHARED, not local (kustos, 2026-10-13). This was a bare exec,
# so a missing interpreter or a missing server surfaced as bash's "line 11: No such file or
# directory" — naming neither the path nor the cause, for three causes needing three fixes
# (venv never created / deploy never ran / caller has a different $HOME). Every launcher in
# the fleet hits the same wall, so the guard lives once in scripts/lib/require-fleet-venv.sh
# and this wrapper only sources it — a per-launcher copy would drift.
set -u

_srv="${HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"

# Resolve the guard: the deployed location first, then beside this script — the wrapper sits
# in scripts/ once deployed and in ops/scripts/manage/ in the repo.
_guard=""
for _cand in \
  "${HOME}/.hermes-cortex/scripts/lib/require-fleet-venv.sh" \
  "$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/lib/require-fleet-venv.sh" \
  "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)/require-fleet-venv.sh"
do
  [[ -f "$_cand" ]] && { _guard="$_cand"; break; }
done

if [[ -z "$_guard" ]]; then
  echo "loop-gov-mcp: the venv guard is NOT DEPLOYED at ${HOME}/.hermes-cortex/scripts/lib/require-fleet-venv.sh" >&2
  echo "  HOME=${HOME}  (a different HOME in the caller is a cause)" >&2
  echo "  deploy it: bash ~/hermes-cortex/ops/scripts/cortex-update.sh" >&2
  exit 78   # EX_CONFIG: the configuration this needs is absent
fi

# shellcheck source=/dev/null
. "$_guard"

# Names which piece is missing — the interpreter, the payload, or a different HOME — and
# prints the fix for that piece, then exits 78.
require_fleet_venv "$_srv"

exec "$(fleet_venv_python)" "$_srv" "$@"
