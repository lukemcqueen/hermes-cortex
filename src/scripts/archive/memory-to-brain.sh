#!/bin/bash
# memory-to-brain.sh — Sync Hermes agent memory → gbrain (long-term brain)
#
# Reads MEMORY.md and USER.md from the active Hermes profile,
# formats them as searchable gbrain pages under ~/brain/shared/hermes-memory/,
# then git-commits so the gbrain sync daemon picks them up.
#
# Designed to run as a cron job (deliver: local) alongside conversation export.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BRAIN_SHARED="$HOME/brain/shared"
MEMORY_DIR="$HERMES_HOME/memories"
OUT_DIR="$BRAIN_SHARED/hermes-memory"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
LOGFILE="$HERMES_HOME/scripts/memory-to-brain.log"

exec > "$LOGFILE" 2>&1

echo "[$TIMESTAMP] === memory-to-brain sync ==="

# --- Read memory files ---
MEMORY_FILE="$MEMORY_DIR/MEMORY.md"
USER_FILE="$MEMORY_DIR/USER.md"

if [ ! -f "$MEMORY_FILE" ] && [ ! -f "$USER_FILE" ]; then
    echo "Neither MEMORY.md nor USER.md found — nothing to sync."
    exit 0
fi

# ── Build current.md (authoritative snapshot) ──
CURRENT="$OUT_DIR/current.md"

cat > "$CURRENT" << 'FM'
---
type: note
tags: [hermes, memory, agent, automation]
---

FM

echo "# Hermes Agent Memory Snapshot" >> "$CURRENT"
echo "" >> "$CURRENT"
echo "_Generated: ${TIMESTAMP}_" >> "$CURRENT"
echo "" >> "$CURRENT"

# MEMORY.md section
if [ -f "$MEMORY_FILE" ] && [ -s "$MEMORY_FILE" ]; then
    echo "## Agent Notes (MEMORY.md)" >> "$CURRENT"
    echo "" >> "$CURRENT"

    # Split on § delimiter, skip empty entries
    awk -v RS='§' '
    NF {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
        if (length($0) > 0) {
            print $0
            print ""
        }
    }' "$MEMORY_FILE" | while IFS= read -r line; do
        if [ -n "$line" ]; then
            echo "$line" >> "$CURRENT"
            echo "" >> "$CURRENT"
        fi
    done
fi

# USER.md section
if [ -f "$USER_FILE" ] && [ -s "$USER_FILE" ]; then
    echo "---" >> "$CURRENT"
    echo "" >> "$CURRENT"
    echo "## User Profile (USER.md)" >> "$CURRENT"
    echo "" >> "$CURRENT"

    awk -v RS='§' '
    NF {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
        if (length($0) > 0) {
            print $0
            print ""
        }
    }' "$USER_FILE" | while IFS= read -r line; do
        if [ -n "$line" ]; then
            echo "$line" >> "$CURRENT"
            echo "" >> "$CURRENT"
        fi
    done
fi

echo "✓ Written: current.md ($(wc -c < "$CURRENT") bytes)"

# ── Also archive a dated copy for history ──
DATE_STAMP="$(date '+%Y-%m')"
ARCHIVE_DIR="$OUT_DIR/archive/$DATE_STAMP"
mkdir -p "$ARCHIVE_DIR"
cp "$CURRENT" "$ARCHIVE_DIR/$(date '+%Y-%m-%d').md"
echo "✓ Archived: $ARCHIVE_DIR/$(date '+%Y-%m-%d').md"

# ── Git commit so sync daemon picks it up ──
cd "$BRAIN_SHARED"

if [ -d .git ]; then
    git add hermes-memory/ 2>/dev/null || true
    # Only commit if there are changes
    if ! git diff --cached --quiet; then
        git commit -m "hermes-memory: auto-sync $(date '+%Y-%m-%d %H:%M')"
        echo "✓ Git committed to shared brain"
    else
        echo "No changes to commit"
    fi
else
    echo "⚠  $BRAIN_SHARED is not a git repo — skipping commit"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === memory-to-brain sync complete ==="
