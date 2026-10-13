#!/usr/bin/env bash
# Wrapper for loop-gov-mcp.py — uses dedicated venv with mcp package
# P1-A hardening (2026-07-31): exec the IMMUTABLE deployed copy
# (~/.hermes-cortex/tools/loop-governance/), NOT the user-writable repo
# working tree. Editing the repo copy must not disable begin_change
# enforcement. The deployed copy is kept current by cortex-update.sh
# (register entry) and locked by hermes-plugin-lock.
#
# FAIL SPECIFICALLY, NOT WITH BASH'S DEFAULT (2026-10-13). This used to be a bare exec, so a
# missing interpreter or a missing server surfaced as "line 11: No such file or directory" —
# naming neither the path nor the cause. On kustos that cost a whole diagnosis: three
# different causes produce that one message, and they need three different fixes:
#   1. the fleet venv was never created (TRUE: nothing in this repo creates it);
#   2. this host's deploy has not run, so the server file is not in the deployed tree;
#   3. the caller runs with a different $HOME — the paths below are relative to it, so a
#      present file looks absent.
# So: say which path is missing, print the HOME seen, and print the fix for that path.
set -u
_py="${HOME}/.hermes-cortex/venv/bin/python3"
_srv="${HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
_venv_dir="${HOME}/.hermes-cortex/venv"

if [[ ! -x "$_py" ]]; then
  echo "loop-gov-mcp: NO INTERPRETER at $_py" >&2
  echo "  HOME=${HOME}  (these paths are relative to HOME; a different HOME in the caller is a cause)" >&2
  echo "  the fleet venv is created by nothing in this repo — create it, then fill it:" >&2
  echo "    python3 -m venv \"${_venv_dir}\"" >&2
  echo "    \"${_venv_dir}/bin/python3\" \"${HOME}/.hermes-cortex/scripts/fix-cortex-venv.py\"" >&2
  echo "  (on a host that has not deployed the fixer: bash ~/hermes-cortex/ops/scripts/cortex-update.sh)" >&2
  exit 78   # EX_CONFIG: the configuration this needs is absent
fi

if [[ ! -f "$_srv" ]]; then
  echo "loop-gov-mcp: the governance server is NOT DEPLOYED at $_srv" >&2
  echo "  HOME=${HOME}  (check this FIRST — a different HOME makes a present file look absent)" >&2
  echo "  deploy it (its register entry lives in cortex-update.sh):" >&2
  echo "    bash ~/hermes-cortex/ops/scripts/cortex-update.sh" >&2
  exit 78
fi

exec "$_py" "$_srv" "$@"
