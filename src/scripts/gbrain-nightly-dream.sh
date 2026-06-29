#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  gbrain-nightly-dream.sh — Weekly knowledge enrichment (dream)
#  Runs: gbrain dream | tail -20 (truncated for cron delivery)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
GBRAIN="$HOME/.bun/bin/gbrain"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: starting"

"$GBRAIN" dream 2>&1 | tail -20

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: done"
