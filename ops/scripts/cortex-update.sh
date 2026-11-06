#!/usr/bin/env bash
# ONE-RELEASE forwarding shim: cortex-update.sh -> fleet-update.sh (P3.cortex->fleet, 2026-11-06).
# The deploy script was renamed to fleet-update.sh. This shim keeps every legacy
# invocation (live crons, documented commands, the sanctioned gate) working for one
# release by forwarding to its sibling. It must be DELETED when the old name retires,
# along with its register() entry and the enforcer's dual-accept branch.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fleet-update.sh" "$@"