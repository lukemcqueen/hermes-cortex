#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  hermes-full-backup.sh — Complete Hermes Agent Data Backup
#
#  Backs up everything NOT in hermes-cortex repo:
#  - Cron jobs (jobs.json + output)
#  - Sessions (conversation history)
#  - Memory (MEMORY.md, USER.md)
#  - Brain directories (knowledge base)
#  - Lessons (agent learnings)
#  - Agent inbox (cross-agent messages)
#  - Config (config.yaml, auth.json)
#  - Eval data
#  - Web cache
#  - Gateway state
#
#  Usage: ./hermes-full-backup.sh [dest_dir]
#  Default dest: ~/hermes-backup-YYYYMMDD_HHMMSS/
# ─────────────────────────────────────────────────────────────
set -euo pipefail

DEST="${1:-$HOME/hermes-backup-$(date +%Y%m%d_%H%M%S)}"
HERMES="$HOME/.hermes"
BRAIN="$HOME/brain"

echo "━━━ Hermes Full Backup ━━━"
echo "Source: $HERMES"
echo "Brain:  $BRAIN"
echo "Dest:   $DEST"
echo ""

mkdir -p "$DEST"

# ── Cron Jobs ───────────────────────────────────────────────
echo "1/12 Backing up cron jobs..."
if [ -d "$HERMES/cron" ]; then
    mkdir -p "$DEST/cron"
    cp "$HERMES/cron/jobs.json" "$DEST/cron/" 2>/dev/null || true
    cp "$HERMES/cron/jobs.json.backup"* "$DEST/cron/" 2>/dev/null || true
    cp "$HERMES/cron/sessions.json" "$DEST/cron/" 2>/dev/null || true
    # Cron output (last 30 days only to save space)
    if [ -d "$HERMES/cron/output" ]; then
        mkdir -p "$DEST/cron/output"
        find "$HERMES/cron/output" -type f -mtime -30 -exec cp {} "$DEST/cron/output/" \; 2>/dev/null || true
        echo "   ✓ Cron jobs + output (last 30 days)"
    fi
fi

# ── Sessions ────────────────────────────────────────────────
echo "2/12 Backing up sessions..."
if [ -d "$HERMES/sessions" ]; then
    mkdir -p "$DEST/sessions"
    cp -r "$HERMES/sessions"/* "$DEST/sessions/" 2>/dev/null || true
    echo "   ✓ Sessions ($(du -m "$DEST/sessions" | cut -f1)MB)"
fi

# ── Memory ──────────────────────────────────────────────────
echo "3/12 Backing up memory..."
if [ -d "$HERMES/memory" ]; then
    mkdir -p "$DEST/memory"
    cp -r "$HERMES/memory"/* "$DEST/memory/" 2>/dev/null || true
    echo "   ✓ Memory files"
fi

# ── Brain Directories ───────────────────────────────────────
echo "4/12 Backing up brain directories..."
if [ -d "$BRAIN" ]; then
    mkdir -p "$DEST/brain"
    # Copy each brain source except symlinks
    for dir in "$BRAIN"/*/; do
        if [ -d "$dir" ] && [ ! -L "$dir" ]; then
            brain_name=$(basename "$dir")
            cp -r "$dir" "$DEST/brain/" 2>/dev/null || true
            echo "   ✓ Brain: $brain_name"
        fi
    done
    # Copy index and resolver
    cp "$BRAIN/RESOLVER.md" "$DEST/brain/" 2>/dev/null || true
    cp "$BRAIN/index.md" "$DEST/brain/" 2>/dev/null || true
fi

# ── Lessons ─────────────────────────────────────────────────
echo "5/12 Backing up lessons..."
if [ -d "$BRAIN/lessons-local-backup" ]; then
    mkdir -p "$DEST/lessons"
    cp -r "$BRAIN/lessons-local-backup"/* "$DEST/lessons/" 2>/dev/null || true
    echo "   ✓ Lessons (local backup)"
fi
# Check if lessons symlink exists and copy target
if [ -L "$BRAIN/lessons" ]; then
    lessons_target=$(readlink "$BRAIN/lessons")
    echo "   → Lessons symlink → $lessons_target"
    if [ -d "$lessons_target" ]; then
        mkdir -p "$DEST/lessons-dropbox"
        cp -r "$lessons_target"/* "$DEST/lessons-dropbox/" 2>/dev/null || true
        echo "   ✓ Lessons (Dropbox mirror)"
    fi
fi

# ── Agent Inbox ─────────────────────────────────────────────
echo "6/12 Backing up agent inbox..."
if [ -d "$HERMES/agent-inbox" ]; then
    mkdir -p "$DEST/agent-inbox"
    cp -r "$HERMES/agent-inbox"/* "$DEST/agent-inbox/" 2>/dev/null || true
    echo "   ✓ Agent inbox messages"
fi
# Inbox configs
for conf in "$HERMES"/agent-inbox-*.conf; do
    if [ -f "$conf" ]; then
        cp "$conf" "$DEST/" 2>/dev/null || true
    fi
done

# ── Config Files ────────────────────────────────────────────
echo "7/12 Backing up config files..."
mkdir -p "$DEST/config"
cp "$HERMES/config.yaml" "$DEST/config/" 2>/dev/null || true
cp "$HERMES/auth.json" "$DEST/config/" 2>/dev/null || true
cp "$HERMES/gateway_state.json" "$DEST/config/" 2>/dev/null || true
cp "$HERMES/channel_directory.json" "$DEST/config/" 2>/dev/null || true
cp "$HERMES/.env" "$DEST/config/" 2>/dev/null || true
cp "$HERMES/SOUL.md" "$DEST/config/" 2>/dev/null || true
echo "   ✓ Config, auth, gateway state"

# ── Eval Data ───────────────────────────────────────────────
echo "8/12 Backing up eval data..."
if [ -d "$HERMES/evals" ]; then
    mkdir -p "$DEST/evals"
    cp -r "$HERMES/evals"/* "$DEST/evals/" 2>/dev/null || true
    echo "   ✓ Eval data"
fi

# ── Web Cache ───────────────────────────────────────────────
echo "9/12 Backing up web cache..."
if [ -f "$HERMES/data/web_cache.sqlite" ]; then
    mkdir -p "$DEST/data"
    cp "$HERMES/data/web_cache.sqlite" "$DEST/data/" 2>/dev/null || true
    echo "   ✓ Web cache ($(du -m "$DEST/data/web_cache.sqlite" | cut -f1)MB)"
fi

# ── Hermes Agent Skills (local overrides) ───────────────────
echo "10/12 Backing up local skills..."
if [ -d "$HERMES/hermes-agent" ]; then
    mkdir -p "$DEST/hermes-agent"
    cp -r "$HERMES/hermes-agent"/* "$DEST/hermes-agent/" 2>/dev/null || true
    echo "   ✓ Hermes agent skills ($(du -m "$DEST/hermes-agent" | cut -f1)MB)"
fi

# ── Hooks ───────────────────────────────────────────────────
echo "11/12 Backing up hooks..."
if [ -d "$HERMES/hooks" ]; then
    mkdir -p "$DEST/hooks"
    cp -r "$HERMES/hooks"/* "$DEST/hooks/" 2>/dev/null || true
    echo "   ✓ Hooks"
fi

# ── Dashboard Data ──────────────────────────────────────────
echo "12/12 Backing up dashboard data..."
if [ -d "$HERMES/dashboard" ]; then
    mkdir -p "$DEST/dashboard"
    cp -r "$HERMES/dashboard"/* "$DEST/dashboard/" 2>/dev/null || true
    echo "   ✓ Dashboard data"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "━━━ Backup Complete ━━━"
echo "Location: $DEST"
echo "Total size: $(du -sh "$DEST" | cut -f1)"
echo ""
echo "Contents:"
du -sh "$DEST"/* 2>/dev/null | sort -hr
