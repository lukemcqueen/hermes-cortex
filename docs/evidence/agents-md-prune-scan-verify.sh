#!/usr/bin/env bash
# Re-runnable push/presence verification for the 2026-10-09 pruning scan cycle.
#
# Records, as raw output, that this cycle's evidence artifacts are published
# and that the cycle's commit is an ancestor of origin/main.
#
# Usage: bash docs/evidence/agents-md-prune-scan-verify.sh [commit]
set -u
REPO="${1:-$HOME/hermes-cortex}"
COMMIT="${2:-094eb051}"   # this cycle's re-runnable-proof commit

cd "$REPO" || exit 1
git fetch origin --quiet

echo "\$ git rev-parse HEAD origin/main"
git rev-parse HEAD origin/main

echo
echo "\$ git merge-base --is-ancestor $COMMIT origin/main && echo \$?"
git merge-base --is-ancestor "$COMMIT" origin/main && echo "0 (is ancestor)"

echo
echo "\$ git ls-tree --name-only origin/main docs/evidence/ | grep prune-scan"
git ls-tree --name-only origin/main docs/evidence/ | grep prune-scan

echo
echo "\$ run the apply proof"
bash docs/evidence/agents-md-prune-scan-2026-10-09.sh "$REPO"
