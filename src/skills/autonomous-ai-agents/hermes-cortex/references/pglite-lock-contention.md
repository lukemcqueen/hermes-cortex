# PGLite Lock Contention — Debugging Workflow

## Problem Statement

Two launchd daemons — `com.gbrain.autopilot` and `com.gbrain.sync-watch` — both need exclusive access to the same PGLite data directory (`~/.gbrain/brain.pglite`). PGLite 0.4.x only supports one connection at a time, so the second process gets a misleading error.

## Error Signature

```
PGLite failed to initialize its WASM runtime.
  Most common cause: the macOS 26.3 WASM bug
  (https://github.com/garrytan/gbrain/issues/223).
  Run `gbrain doctor` for a full diagnosis.
  Original error: Aborted(). Build with -sASSERTIONS for more info.
```

Despite the error message pointing at a macOS WASM bug, the actual cause on macOS 14.x (NOT 26.3) is almost always **lock contention**: the autopilot has the exclusive PGLite lock and sync-watch can't open a second connection.

## Diagnosis Flow

### 1. Check which daemons are running

```bash
launchctl list | grep gbrain
```

**Healthy state (autopilot only):**
```
63367  0  com.gbrain.autopilot
```

**Contended state (both daemons):**
```
58462  0  com.gbrain.sync-watch     ← failing every cycle
63367  0  com.gbrain.autopilot      ← holding the lock
```

### 2. Check autopilot logs for sync activity

```bash
tail -50 ~/.gbrain/autopilot.log
```

Healthy autopilot shows regular cycles every ~150s:
```
[cycle] score=45 elapsed=0s next=150s
Embedded 0 chunks (0 stale found)
[cycle-inline partial] lint=0 backlinks=0 synced=0 extracted=0 embedded=0 orphans=225
```

`synced=0` is expected when all content is already indexed. The key signal is that cycles run every 150s without errors.

### 3. Check sync-watch logs for the contention error

```bash
tail -20 ~/.gbrain/sync-watch.log
```

Expected pattern when contention occurs:
```
[date] === Sync cycle (0 source(s)) ===
PGLite failed to initialize its WASM runtime.
...
[date] === Cycle complete, sleeping 120s ===
```

The `0 source(s)` output is also a tell: `count_sources()` runs `gbrain sources list` which also fails with WASM error, so the script thinks there are no sources registered.

### 4. Run `gbrain doctor` for a indirect health check

```bash
gbrain doctor
```

If autopilot holds the lock, doctor falls back to filesystem-only checks:
```
[WARN] connection → Could not connect to configured DB; filesystem checks only
Brain checks:  95/100  (category penalty)
Overall health score: 85/100
```

This is a "degraded but working" state — filesystem checks pass, but DB connection is blocked.

### 5. Check PGLite directly via lsof

```bash
lsof -p <autopilot-pid> | grep pglite | head -5
```

Shows which data files the autopilot has open — confirms exclusive access:
```
bun.exe <pid>  ... ~/.gbrain/brain.pglite/base/5/16875
bun.exe <pid>  ... ~/.gbrain/brain.pglite/base/5/17744
```

## Root Cause

The `install.sh` in hermes-cortex creates a `sync-watch` daemon (`com.gbrain.sync-watch`) via `src/scripts/install-gbrain-sync.sh`. Separately, gbrain's own `autopilot` command (run via `gbrain autopilot --install`) creates `com.gbrain.autopilot`. Both daemons try to open the same PGLite database, but PGLite 0.4.x is single-connection.

## Fix (as of commit 7f2205d)

### New installs — automatic

The installer now detects if `com.gbrain.autopilot` is already present and **skips** sync-watch setup:

```bash
# install-gbrain-sync.sh (relevant logic)
if service_running "com.gbrain.autopilot"; then
  info "gbrain autopilot detected — autopilot handles sync internally, skipping sync-watch"
  return 0
fi
```

### Existing installs with both daemons — manual cleanup

```bash
# 1. Stop and disable sync-watch
launchctl bootout gui/$(id -u)/com.gbrain.sync-watch 2>/dev/null || true
mv ~/Library/LaunchAgents/com.gbrain.sync-watch.plist{,.disabled}
mv ~/.gbrain/sync-watch.sh{,.bak}

# 2. Verify only autopilot remains
launchctl list | grep gbrain
# Expected: <pid>  0  com.gbrain.autopilot

# 3. Verify autopilot is working
tail -5 ~/.gbrain/autopilot.log
# Expected: [cycle] score=... elapsed=... next=150s

# 4. Tidy up stale log files
rm -f ~/.gbrain/sync-watch.log ~/.gbrain/sync-watch.err
rm -f ~/.gbrain/sync-watch-stdout.log ~/.gbrain/sync-watch-stderr.log
rm -f ~/.hermes/logs/com.gbrain.sync-watch.log
```

## Verification

After cleanup, confirm:

```bash
# Sync-watch is gone
launchctl list com.gbrain.sync-watch 2>&1
# Expected: "Could not find service..."

# Autopilot is running
launchctl list com.gbrain.autopilot | grep PID
# Expected: "PID" = <number>

# gbrain stats work (briefly stop autopilot, run command, restart)
launchctl bootout gui/$(id -u)/com.gbrain.autopilot 2>/dev/null
sleep 2
gbrain stats
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.autopilot.plist
```

## Files Modified (commit 7f2205d)

| File | Change |
|---|---|
| `src/scripts/install-gbrain-sync.sh` | Skip sync-watch setup if autopilot plist/process exists |
| `src/scripts/cortex-update.sh` | Restart autopilot instead of sync-watch when autopilot present |
| `src/scripts/cortex-health.sh` | Check autopilot first, fall back to sync-watch |
| `src/scripts/heartbeat.py` | Same autopilot-first check |
| `src/dashboard/server.py` | Include autopilot in sync daemon PID regex |
| `install.sh` | Update verify script + install summary output |

## Why Not Just Fix sync-watch?

The autopilot is a self-maintaining daemon that already handles sync internally every ~150s alongside extract, embed, lint, and backlinks. The sync-watch is a simpler bash script that only polls `gbrain sync`. The autopilot is the intended future path — it does everything sync-watch does plus more. Running both is never correct.

## Additional Signals

- If `gbrain sources list` and `gbrain stats` fail but `gbrain doctor` works, the DB connection is being held by another process (doctor does filesystem-only checks)
- If no gbrain daemon at all is running, the PGLite database file itself may be corrupt — see references/gbrain-source-migration-export.md for recovery

---

## Stop/Dream/Restart Pattern (Linux — no systemd service)

On this machine (Linux Mint), the autopilot is launched as a background `bun` process
via `terminal(background=true)`, not as a systemd service. Any cron job that needs
exclusive DB access (e.g., `gbrain dream`) must stop the autopilot first and restart it
afterward.

### The Pattern

The canonical implementation lives in `~/.hermes/scripts/gbrain-nightly-dream.sh`:

```bash
# 1. Stop the autopilot (graceful SIGTERM, 10s timeout, force SIGKILL)
AUTOPILOT_PID=$(pgrep -f 'gbrain.*autopilot' | head -1)
kill -TERM "$AUTOPILOT_PID"
# wait up to 10s, then kill -KILL if still alive

# 2. Run the DB-dependent command
gbrain dream 2>&1 | tail -20

# 3. Restart autopilot (via EXIT trap — always runs)
trap 'if ! pgrep -f "gbrain.*autopilot"; then
      cd $HOME && nohup bun $(which gbrain) autopilot --repo ... &
      fi' EXIT
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **trap on EXIT** | Guarantees autopilot restart even if `gbrain dream` crashes mid-pipeline |
| **pgrep for restart check** | Handles edge cases: dream spawns autopilot, or another process restarts it |
| **SIGTERM first, 10s timeout, then SIGKILL** | Gives autopilot a chance to flush state before force kill |
| **tail -20 on output** | Follows cron truncation convention — full output would be wasteful |

### When to Use

Apply this pattern to any cron that calls `gbrain <command>` and needs DB access
while the autopilot is running. Commands that require the lock:

- `gbrain dream` — full pipeline (sync, embed, synthesize, patterns, consolidate)
- `gbrain sync` — manual sync cycle
- `gbrain stats` — database statistics
- `gbrain sources list` — reads registered sources from DB

Commands that do NOT need the lock (safe to run with autopilot):

- `gbrain doctor --fast` — filesystem-only checks
- `gbrain check-update` — network check, no DB
- `gbrain upgrade` — binary self-update, no DB

---

## Linux (systemd) Differences

The existing docs cover macOS (launchd). On Linux, the same PGLite lock contention
applies, but service management differs.

### Service Management

| Action | macOS (launchd) | Linux (systemd user) |
|--------|-----------------|---------------------|
| List services | `launchctl list \| grep gbrain` | `systemctl --user list-units \| grep gbrain` |
| Check status | `launchctl list com.gbrain.sync-watch` | `systemctl --user is-active com.gbrain.sync-watch` |
| Stop service | `launchctl bootout gui/$(id -u)/...` | `systemctl --user stop ...` |
| Disable service | `mv plist{,.disabled}` | `systemctl --user disable ...` |
| View logs | `tail ~/.gbrain/sync-watch.log` | Same path, or `journalctl --user -u ...` |

### Two Approaches (choose ONE)

**A) sync-watch only (recommended for PGLite)** — Simple bash daemon that
polls `gbrain sync --all` every 120s. Pre-installed by `install.sh`. Works
well with PGLite because it opens and releases the database connection quickly.

```bash
# Enable and start
systemctl --user enable com.gbrain.sync-watch.service
systemctl --user start com.gbrain.sync-watch.service

# Verify
systemctl --user is-active com.gbrain.sync-watch.service
# Expected: active
```

**B) Autopilot only (requires Supabase/network Postgres)** — Full self-
maintaining daemon. **Do NOT use with PGLite** — the exclusive lock blocks
all other gbrain CLI commands (query, sources list, stats) for ~3min every
5min cycle.

```bash
# Install (requires --repo for PGLite brains)
gbrain autopilot --install --repo ~/brain/default --interval 300

# Uninstall
gbrain autopilot --uninstall
systemctl --user stop gbrain-autopilot.service
```

**Never run both.** PGLite is single-connection — autopilot and sync-watch
will fight over the lock and fail intermittently with the WASM error.

### Sync-Watch Resilience

The sync-watch script (`~/.gbrain/sync-watch.sh`) includes a `||` fallback
so transient WASM/PGLite failures don't kill the loop:

```bash
"$BUN" "$GBRAIN" sync --all --no-pull 2>&1 || \
  echo "[$(date)] ⚠ sync failed, will retry next cycle"
```

The service will always be `active (running)` even when an individual sync
cycle fails — systemd only restarts it on process exit.

### Auto-remediation Alert

The `system-alert-watchdog.py` checks the service status (`systemctl --user
is-active`), not individual sync results. A healthy sync-watch service
always reports UP even if a transient WASM error occurred on a cycle.

To verify functional health separately:
```bash
# Run one sync cycle manually
gbrain sync --all --no-pull 2>&1
# Expected: "synced=0" or "imported=N" — any WASM error means lock contention
```

### Full Cleanup (switching between approaches)

```bash
# Stop and disable sync-watch
systemctl --user stop com.gbrain.sync-watch.service
systemctl --user disable com.gbrain.sync-watch.service

# Or stop autopilot
gbrain autopilot --uninstall
systemctl --user stop gbrain-autopilot.service

# Verify no gbrain services remain
systemctl --user list-units | grep gbrain
```

> **Note:** The "macOS 26.3 WASM bug" error message is misleading on Linux too. On both platforms, PGLite lock contention produces the same WASM runtime error text — treat any "PGLite failed to initialize its WASM runtime" error as lock contention first, WASM bug second.
