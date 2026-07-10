# gbrain PGLite Recovery & Maintenance Guide

## Overview

gbrain uses **PGLite** — PostgreSQL compiled to WASM running inside Bun. It's single-connection, which means:
- Only ONE process can access the database at a time
- The autopilot daemon holds the exclusive lock while running
- Any CLI command (`gbrain stats`, `gbrain dream`, `gbrain sources list`) will **fail or hang** if the autopilot is running
- The error message is misleading: "PGLite failed to initialize its WASM runtime" actually means **lock contention**, not a WASM bug

This guide covers **three failure modes** with PGLite and their recovery procedures.

---

## Table of Contents

1. [Failure Mode 1: Stale postmaster.pid — Every CLI Starts In-Memory](#failure-mode-1-stale-postmasterpid--every-cli-starts-in-memory)
2. [Failure Mode 2: Embedding Timeout on Large Documents](#failure-mode-2-embedding-timeout-on-large-documents)
3. [Failure Mode 3: Two Autopilot Instances Fighting for the Same DB](#failure-mode-3-two-autopilot-instances-fighting-for-the-same-db)
4. [Recovery: Full Database Rebuild](#recovery-full-database-rebuild)
5. [Systemd Service for Autopilot (Linux)](#systemd-service-for-autopilot-linux)
6. [Cron Script Pattern: Stop → Dream → Restart](#cron-script-pattern-stop--dream--restart)
7. [Embedding Model Configuration](#embedding-model-configuration)
8. [Verification Commands](#verification-commands)

---

## Failure Mode 1: Stale postmaster.pid — Every CLI Starts In-Memory

### Symptoms

Every `gbrain` command runs all 114 migrations:
```
Schema version 1 → 119 (114 migration(s) pending)
[2] slugify_existing_pages...
[2] ✓ slugify_existing_pages
...
```

And `gbrain stats` always shows `0 pages` even after importing content in a previous session. Data doesn't survive between process restarts.

### Root Cause

When a PGLite instance crashes (process killed with `SIGKILL`, server power loss, etc.), it leaves a **stale `postmaster.pid`** file in the data directory. This file identifies the PostgreSQL instance that owns the data directory. On next start:

- A new PGLite instance sees the existing `postmaster.pid`
- It assumes another PostgreSQL is already running on this data directory
- It falls back to **in-memory-only mode** — creates a fresh database without touching the disk files
- All operations (import, embed, dream) happen in memory and are lost when the process exits
- The disk data is never read or written, even though the files are intact

### Diagnosis

```bash
# Check for stale postmaster.pid
cat ~/.gbrain/brain.pglite/postmaster.pid
# Expected: shows -42 (PGLite identifier) OR a PID of a running process
# Stale: shows a PID from a dead process

# Check if WAL is being written
ls -la ~/.gbrain/brain.pglite/pg_wal/
# If all files are weeks old, no writes have persisted since that date

# Check if the DB is actually persisting
gbrain apply-migrations --yes
# Run it TWICE. If first says "114 applied" and second says "All up to date" → persistence works
# If every run says "114 migration(s) applied" → persistence broken, stale postmaster.pid
```

### Fix

```bash
# 1. Stop ANY gbrain processes (autopilot, sync-watch, CLI sessions)
launchctl bootout gui/$(id -u)/com.gbrain.autopilot 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true
sleep 2
# On Linux with systemd:
systemctl --user stop gbrain-autopilot 2>/dev/null || true
# Fallback for rogue processes:
pkill -f 'gbrain.*autopilot' 2>/dev/null || true
sleep 2

# 2. Remove the stale postmaster.pid
rm -f ~/.gbrain/brain.pglite/postmaster.pid

# 3. The DB is still intact! Run migrations to verify
gbrain apply-migrations --yes
# If this says "All migrations up to date" — data is intact, you're done
# If it says "114 migration(s) applied" — data was in-memory, need recovery
```

**If persistence is still broken** after removing postmaster.pid, the WAL/checkpoint state is corrupted. See [Full Database Rebuild](#recovery-full-database-rebuild).

---

## Failure Mode 2: Embedding Timeout on Large Documents

### Symptoms

```
Error embedding <slug>: [embed(ollama:nomic-embed-text:v1.5)] The operation timed out.
```

Some pages get embedded (showing progress percentages like "10/110 (9%)") but then fail partway through.

### Root Cause

gbrain has a **default 60-second timeout** for each embedding API call (defined as `AI_EMBED_TIMEOUT_MS = 60_000` in `src/core/ai/gateway.ts`). Ollama's `nomic-embed-text:v1.5` takes longer than 60s for large documents (daily memory files, long reference docs, multi-page lessons).

### Fix

Set `GBRAIN_AI_EMBED_TIMEOUT_MS=300000` (5 minutes) in:
  - All cron scripts that call gbrain
  - The autopilot startup script (`autopilot-run.sh`)
  - Any shell that runs gbrain embed commands

```bash
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
gbrain embed --stale
```

To make it permanent, add to `~/.gbrain/autopilot-run.sh` and all cron scripts:

```bash
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
```

### Which Files to Patch

| File | Step |
|------|------|
| `~/.gbrain/autopilot-run.sh` | Add `export GBRAIN_AI_EMBED_TIMEOUT_MS=300000` before `exec` |
| `~/.hermes/scripts/gbrain-nightly-dream.sh` | Add after `export PATH=...` line |
| `~/.hermes/scripts/gbrain-update-sync.sh` | Same |
| Any new gbrain cron script | Add during creation |

---

## Failure Mode 3: Two Autopilot Instances Fighting for the Same DB

### Symptoms

```
Autopilot stopping (SIGTERM).
```
appears unexpectedly in the autopilot log, or the autopilot cycles restart every few seconds.

### Root Cause

Two `gbrain autopilot` processes were started for different repos (e.g., `--repo /home/user/brain/hermes-cortex` and `--repo /home/user/brain`) but both use the **same PGLite database** at `~/.gbrain/brain.pglite/`. Since PGLite is single-connection, only one can hold the lock. The second one either starts in-memory or crashes.

### Diagnosis

```bash
ps aux | grep -E '[g]brain.*autopilot'
# If TWO lines appear with different --repo paths, you have the problem
```

### Fix

```bash
# Kill ALL autopilot instances
pkill -f 'gbrain.*autopilot' 2>/dev/null || true
sleep 2

# Verify none remain
ps aux | grep -E '[g]brain.*autopilot' | grep -v grep || echo "clean"

# Restart ONLY ONE, pointing to the main brain repo
# Either via systemd:
systemctl --user start gbrain-autopilot.service
# Or via launchd:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.autopilot.plist

# Verify only one process
ps aux | grep -E '[g]brain.*autopilot' | grep -v grep
```

**Prevention:** Never run two autopilots. A single `--repo ~/brain` covers all subdirectories.

---

## Recovery: Full Database Rebuild

Use this when:

- Persistence is broken (every `gbrain` command runs 114 migrations)
- `gbrain stats` shows 0 pages even after import
- The WAL hasn't been modified in weeks
- Removing `postmaster.pid` didn't fix it

### Step 1: Stop All gbrain Processes

```bash
# Linux (systemd)
systemctl --user stop gbrain-autopilot.service 2>/dev/null || true

# macOS (launchd)
launchctl bootout gui/$(id -u)/com.gbrain.autopilot 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true

# Universal
pkill -f 'gbrain.*autopilot' 2>/dev/null || true
sleep 3
ps aux | grep -E '[g]brain' | grep -v grep || echo "all gbrain processes dead"
```

### Step 2: Backup and Remove Old Database

```bash
OLD_BACKUP=~/.gbrain/brain.pglite.bak.$(date +%s)
mv ~/.gbrain/brain.pglite "$OLD_BACKUP"
echo "Backed up to $OLD_BACKUP"
```

### Step 3: Reinitialize from Scratch

```bash
gbrain init --pglite
```

**What this does:**
- Creates a fresh PGLite database at `~/.gbrain/brain.pglite/`
- Runs all 114 schema migrations (v1 → v119)
- Properly syncs the migration tracking table to disk
- Configures the embedding model from `~/.gbrain/config.json`
- Sets search mode (respond to prompts if asked)

### Step 4: Verify Persistence

Run `apply-migrations` **twice**:

```bash
# First run — applies migrations
gbrain apply-migrations --yes
# Expected output: "All migrations up to date."

# Second run — proves persistence
gbrain apply-migrations --yes
# Expected output: "All migrations up to date."
# If this shows "114 migration(s) pending", persistence is STILL broken
```

### Step 5: Import Brain Content

```bash
gbrain import ~/brain
```

**What this does:**
- Scans `~/brain/` for `.md` files
- Creates pages in the `default` source (federated)
- Generates content chunks for embedding
- Reports: `X pages imported, Y chunks created`

### Step 6: Embed All Chunks

```bash
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
gbrain embed --all
```

**Note:** `--all` embeds every chunk. `--stale` embeds only chunks whose content has changed. Use `--all` after a fresh import, `--stale` for routine maintenance.

### Step 7: Register Additional Sources

```bash
gbrain sources list
# Records each content area as a searchable source
for d in ~/brain/*/; do
  name=$(basename "$d")
  [ -d "$d/.git" ] && gbrain sources add "$name" --path "$d"
done
```

### Step 8: Verify Final State

```bash
gbrain stats
# Expected: Pages > 0, Chunks = Pages × ~2, Embedded = Chunks
gbrain apply-migrations --yes
# Expected: "All migrations up to date."
```

### Step 9: Restart Autopilot

```bash
# Linux (systemd)
systemctl --user start gbrain-autopilot.service

# macOS (launchd)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.autopilot.plist

# Verify
ps aux | grep -E '[g]brain.*autopilot' | grep -v grep
```

### Step 10: Clean Up Backup

After confirming the new database works:

```bash
rm -rf "$OLD_BACKUP"
```

### Expected Time

| Step | Duration |
|------|----------|
| Stop processes | ~10s |
| gbrain init | ~30-60s (114 migrations) |
| Verify persistence | ~5s |
| Import brain content | ~5-30s (depends on file count) |
| Embed all chunks | ~2-5 min (with 5-min timeout per chunk) |
| Register sources | ~5s |
| Verify | ~5s |
| Restart autopilot | ~5s |
| **Total** | **~3-8 min** |

---

## Systemd Service for Autopilot (Linux)

On Linux systems, create a systemd **user service** so the autopilot auto-starts on boot.

### Service File

Save to `~/.config/systemd/user/gbrain-autopilot.service`:

```ini
[Unit]
Description=gbrain autopilot — self-maintaining brain daemon
Documentation=https://github.com/garrytan/gbrain
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
ExecStart=%h/.gbrain/autopilot-run.sh
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

Environment=GBRAIN_AI_EMBED_TIMEOUT_MS=300000

[Install]
WantedBy=default.target
```

### Enable and Start

```bash
# Create directory (if not exists)
mkdir -p ~/.config/systemd/user/

# Write the service file (content above)
# Or install via cortex-update.sh

# Reload, enable, start
systemctl --user daemon-reload
systemctl --user enable gbrain-autopilot.service
systemctl --user start gbrain-autopilot.service

# Verify
systemctl --user status gbrain-autopilot.service --no-pager
```

### Ensure Linger

User services only start at boot if `linger` is enabled:

```bash
loginctl show-user $(whoami) | grep Linger
# If "Linger=no":
sudo loginctl enable-linger $(whoami)
```

### Verify on Reboot

After a server reboot:

```bash
systemctl --user status gbrain-autopilot.service --no-pager
# Expected: "active (running)"
gbrain stats
# Expected: same page/chunk/embedded counts as before reboot
```

---

## Cron Script Pattern: Stop → Dream → Restart

Any cron script that calls `gbrain dream` or `gbrain sync` MUST follow the **stop-autopilot → run command → restart-autopilot** pattern because PGLite is single-connection.

### Canonical Pattern

```bash
#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  Canonical gbrain cron pattern
#  All agents: copy this pattern for any cron that calls gbrain CLI
#  while the autopilot is running.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
GBRAIN="$HOME/.bun/bin/gbrain"
GBRAIN_REPO="$HOME/brain"

echo "[$(date)] gbrain job: starting"

# ── Helpers ──────────────────────────────────────────────────────────
find_autopilot_pid() {
    pgrep -f 'gbrain.*autopilot' 2>/dev/null | head -1 || true
}
autopilot_is_dead() { [ -z "$(find_autopilot_pid)" ]; }
start_autopilot() {
    cd "$HOME"
    nohup "$GBRAIN" autopilot --repo "$GBRAIN_REPO" > /dev/null 2>&1 &
    echo "  Autopilot restarted (PID $!)"
}

# ── Trap: guarantee autopilot restart ────────────────────────────────
autopilot_restart_handler() {
    local EXIT_STATUS=$?
    if autopilot_is_dead; then
        echo "  [trap] Autopilot not running — restarting..."
        start_autopilot
    else
        echo "  [trap] Autopilot already running"
    fi
    return "$EXIT_STATUS"
}
trap autopilot_restart_handler EXIT

# ── Step 1: Stop the autopilot ──────────────────────────────────────
AUTOPILOT_PID=$(find_autopilot_pid)
if [ -n "$AUTOPILOT_PID" ]; then
    echo "  Found autopilot PID $AUTOPILOT_PID — stopping..."
    kill -TERM "$AUTOPILOT_PID" 2>/dev/null || true
    for i in $(seq 1 10); do
        if autopilot_is_dead; then
            echo "  Autopilot stopped (took ${i}s)"
            break
        fi
        sleep 1
    done
    if ! autopilot_is_dead; then
        echo "  ⚠ Graceful stop failed — force killing..."
        kill -KILL "$AUTOPILOT_PID" 2>/dev/null || true
        sleep 1
    fi
fi

# ── Step 2: Run the gbrain command ──────────────────────────────────
echo "  Running gbrain <command>..."
CMD_EXIT=0
"$GBRAIN" <command> 2>&1 | tail -20 || CMD_EXIT=$?

echo "  gbrain <command> completed (exit=$CMD_EXIT)"
echo "[$(date)] gbrain job: done"
```

### Why This Pattern Is Required

- PGLite can only have **one open connection** at a time
- The autopilot holds the lock for its full ~150s cycle
- Without stopping it, `gbrain dream` or `gbrain sync` creates a new PGLite instance that starts **in memory** — writes are lost on exit
- The trap handler guarantees the autopilot is restarted even if the dream command fails (crash safety)

### Which Cron Scripts Need This

| Script | Command | Patched? |
|--------|---------|----------|
| `gbrain-nightly-dream.sh` | `gbrain dream` | ✅ Since July 2026 |
| `gbrain-update-sync.sh` | `gbrain upgrade` + `gbrain doctor` | ⚠️ Add if running while autopilot is active |
| Any new gbrain cron | Follow this pattern | — |

---

## Embedding Model Configuration

### The `:v1.5` Tag Requirement

**Always use the explicit tag `nomic-embed-text:v1.5`**, NOT `nomic-embed-text:latest`.

When `:latest` is pulled, it resolves to `nomic-embed-text:latest` which is the same digest as `v1.5`. However, gbrain and the Ollama client check the **exact model name** against what's available. If the config says `nomic-embed-text` (no tag) and only `nomic-embed-text:v1.5` is installed, the API call returns a model-not-found error.

**The fix:** Update both config locations:

```bash
# ~/.gbrain/config.json
"embedding_model": "ollama:nomic-embed-text:v1.5"

# ~/.hermes/hermes-cortex.env
EMBEDDING_MODEL=nomic-embed-text:v1.5
```

### Where gbrain Reads the Embedding Model

| Config Source | Priority | Example |
|--------------|----------|---------|
| `~/.gbrain/config.json` | Highest | `"embedding_model": "ollama:nomic-embed-text:v1.5"` |
| CLI command line | Medium | `gbrain embed --model ollama:nomic-embed-text:v1.5` |
| Default (in code) | Lowest | `ollama:nomic-embed-text` |

After changing the config, **restart the autopilot** so it picks up the new model.

### Verify the Model Works

```bash
# Direct API test
curl -s http://localhost:11434/api/embeddings \
  -d '{"model":"nomic-embed-text:v1.5","prompt":"test"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"embedding\"])}d embedding OK')"
# Expected: "768d embedding OK"

# gbrain test
gbrain search "test" 2>&1 | head -5
# Expected: returns results or "no results" — no error about missing model
```

### What Happens When It's Wrong

- Autopilot cycles: `Embedded 0 chunks (0 stale found)` — chunks exist but can't be embedded
- `gbrain embed --all`: All chunks fail with `[embed(ollama:nomic-embed-text)] Error` (no tag → no match)
- `gbrain stats`: Shows `Chunks > 0` but `Embedded = 0`

If you see this pattern, check the config and fix the model tag.

---

## Verification Commands

Use these to confirm the brain is healthy after any recovery:

```bash
# 1. Core stats
gbrain stats
# Expected: Pages > 0, Chunks > 0, Embedded = Chunks

# 2. Migration persistence (run twice)
gbrain apply-migrations --yes
gbrain apply-migrations --yes
# Both runs: "All migrations up to date."

# 3. Dream cycle (simulates nightly cron)
GBRAIN_AI_EMBED_TIMEOUT_MS=300000 gbrain dream 2>&1 | tail -10
# Expected: "✓ embed 0 chunk(s) newly embedded (0 already had embeddings)"

# 4. Search
gbrain search "test" --limit 1 2>&1

# 5. Sources
gbrain sources list
# Expected: default (110 pages) + any named sources

# 6. Autopilot service
systemctl --user is-active gbrain-autopilot.service 2>/dev/null || echo "check manually"
ps aux | grep -E '[g]brain.*autopilot' | grep -v grep

# 7. Database file integrity
ls -la ~/.gbrain/brain.pglite/pg_wal/
# WAL files should be from today (recent)
```

---

## Quick Reference: Common Commands

| Command | When |
|---------|------|
| `gbrain stats` | Overall brain health |
| `gbrain sources list` | Check registered sources + page counts |
| `gbrain import ~/brain` | First-time content import |
| `gbrain embed --all` | Full re-embed (after model change or import) |
| `GBRAIN_AI_EMBED_TIMEOUT_MS=300000 gbrain embed --stale` | Incremental re-embed |
| `gbrain dream` | Full maintenance cycle (sync, extract, embed, consolidate) |
| `gbrain apply-migrations --yes` | Apply pending schema migrations |
| `gbrain doctor --fast` | Health check |
| `systemctl --user status gbrain-autopilot` | Autopilot daemon status (Linux) |
| `launchctl list \| grep gbrain` | Autopilot daemon status (macOS) |
