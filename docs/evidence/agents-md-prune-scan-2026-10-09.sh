#!/usr/bin/env bash
# Re-runnable proof for the 2026-10-09 AGENTS.md pruning scan.
# Source: hermes-cortex docs/evidence/agents-md-prune-scan-2026-10-09.txt
#
# Executes the EXACT command and records its raw output + exit code, plus the
# byte-identical AGENTS.md check. Run from anywhere:
#   bash <repo>/docs/evidence/agents-md-prune-scan-2026-10-09.sh
set -u
REPO="${1:-$HOME/hermes-cortex}"
AUDIT="$HOME/.hermes-cortex/scripts/agents-doc-audit.py"

echo "\$ python3 $AUDIT --repo $REPO --prune --apply"
python3 "$AUDIT" --repo "$REPO" --prune --apply
echo "exit=$?"

echo
echo "=== AGENTS.md byte-identical check (apply with 0 candidates is a no-op) ==="
echo "\$ git -C $REPO status --short AGENTS.md"
git -C "$REPO" status --short AGENTS.md
echo "(empty above = AGENTS.md unchanged)"
echo "\$ git -C $REPO diff --stat AGENTS.md"
git -C "$REPO" diff --stat AGENTS.md
echo "(empty above = no diff)"
