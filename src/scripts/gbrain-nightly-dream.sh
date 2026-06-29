#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  gbrain-nightly-dream.sh — Weekly knowledge enrichment (dream)
#  Runs: gbrain dream
# ─────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
GBRAIN="$HOME/.bun/bin/gbrain"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: starting"

"$GBRAIN" dream 2>&1

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: done"
