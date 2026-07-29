---
name: gbrain-maintenance
version: 2.0.0
category: devops
description: "Manage gbrain knowledge brain lifecycle — autopilot daemon, sync, dream cycle, service control, and cron integration."
author: Hermes Cortex
license: MIT
---

# gbrain Maintenance

Manage a gbrain knowledge brain on a Hermes agent: install the autopilot daemon, run one-shot syncs, trigger dream cycles, and integrate with cron for the serendipity layer.

## Core commands

| Action | Command | When |
|--------|---------|------|
| **Install autopilot daemon** | `gbrain autopilot --install --repo <path>` | First-time setup |
| **Uninstall autopilot** | `gbrain autopilot --uninstall` | Moving to a different setup |
| **One-shot sync** | `gbrain sync` | Manual import after editing brain repo |
| **Full re-sync** | `gbrain sync --full` | After schema changes or corruption |
| **Health check** | `gbrain doctor --json` | Verify everything is working |
| **Dream cycle** | `gbrain dream` | Nightly 8-phase maintenance (entity sweep, citations, consolidation) |
| **List fresh pages** | `gbrain list -n 20` | See what's new across the brain |
| **Query the brain** | `gbrain ask <question>` | Find connections between topics |
| **Search** | `gbrain search <query>` | Hybrid keyword/semantic search |
| **View config** | `cat ~/.gbrain/config.json` | Check engine, repo, embedding settings |
| **Service status** | `systemctl --user status gbrain-autopilot.service` (systemd) or `pgrep -f 'gbrain.*autopilot'` (bg process) | Verify daemon is running |
| **Service logs** | `tail -f ~/.gbrain/autopilot.log` | Watch live output |
| **Service errors** | `cat ~/.gbrain/autopilot.err` | Check for issues |

## What autopilot handles

`gbrain autopilot --install` sets up a **systemd user service** that:

| Cycle | Frequency | What it does |
|-------|-----------|-------------|
| **Sync** | Every 15 min | `gbrain sync --repo <path>` + `gbrain embed --stale` — imports changes from git |
| **Update check** | Daily | `gbrain check-update --json` — reports available updates (never auto-installs) |
| **Dream** | Nightly | `gbrain dream` — 8-phase maintenance (entity sweep, citation fixes, memory consolidation, conversation synthesis, cross-session pattern detection) |

## The autopilot + creative cron pattern

The recommended setup is **autopilot daemon + one light cron** for the serendipity layer:

```
gbrain-autopilot.service          → sync every 15min, dream nightly (backstage)
gbrain-creative-dream (cron)      → creative ~200 word summary, weekly (user-facing)
```

The cron's job is NOT to sync or maintain — autopilot does that. The cron just:
1. Lists recent pages (`gbrain list -n 20`)
2. Picks 3-5 related topics
3. Finds connections (`gbrain ask` or `gbrain search`)
4. Writes a warm ~200 word "dream summary"

### Sample cron prompt

```
Run a light creative gbrain dream. Autopilot already handles sync and nightly maintenance — this is just the serendipity layer.

1. `gbrain list -n 20` — see what's fresh across the brain
2. Pick 3-5 topics/pages that seem related or interesting
3. Use `gbrain ask` or `gbrain search` to find connections between them
4. Write a brief, warm "dream" summary (~200 words) highlighting insights, patterns, or connections

Keep it warm and thoughtful, not dry. Think of it as the brain telling us something interesting.

## QUALITY GATE — CRITICAL
Before delivering, self-check:
1. Is the output useful, readable, and on-topic?
2. Did you run actual tools, not fabricate results?
3. Is it the right length (~200 words, not oversized)?
If ANY answer is NO → output EXACTLY this one line:
QUALITY_G_BLOCKED

If all YES → deliver as normal.
```

## Installation steps

```bash
# 1. Find the brain repo
ls ~/brain/*/  # Usually ~/brain/<agent-name>/

# 2. Install autopilot with correct repo path
gbrain autopilot --install --repo ~/brain/moses

# 3. Verify it's running
systemctl --user status gbrain-autopilot.service

# 4. Create the creative cron (see template above)
#    Pin it so the drift guard doesn't block it
cronjob action=create name=gbrain-creative-dream \
  schedule="0 3 * * 6" \
  provider=openrouter model=deepseek/deepseek-v4-flash \
  prompt="..."
```

## Replacing old crons with autopilot

Before moving to autopilot, you may have separate crons:

| Old cron | What it did | Action |
|----------|-------------|--------|
| `gbrain-update-sync` | `gbrain sync` + `gbrain doctor` weekly | Remove — autopilot handles this every 15 min |
| `gbrain-nightly-dream` | Full creative dream summary | Replace with lighter cron (see template above) |

```bash
cronjob action=remove job_id=<sync-cron-id>
cronjob action=update job_id=<dream-cron-id> name=gbrain-creative-dream prompt="..."
```

## Embedding Model Configuration

gbrain vectorizes brain pages using a local Ollama embedding model. The model is set in two places:

| Location | Key | Example |
|----------|-----|---------|
| `~/.gbrain/config.json` | `embedding_model` | `ollama:nomic-embed-text:v1.5` |
| `~/.hermes/models.env` | `EMBEDDING_MODEL` | `nomic-embed-text:v1.5` |

**Current recommended model:** `nomic-embed-text:v1.5` — 274 MB, 768 dims, native 8192-token context. Drop-in replacement for `nomic-embed-text` (v1), which had only 2048-token context and returned empty embeddings for pages over ~500 words.

See **`references/embedding-models.md`** for model comparison, swap procedure, and cold-start handling.
See **`references/pglite-wasm-kernel7.md`** for the full kernel 7.0 diagnosis record including service logs, error transcripts, and the fix verification steps.

### PGLite WASM crash on Linux — fix with PGLite 0.5.4

On some kernel versions (Linux 6.8.0 observed, Intel i3-12100), PGLite 0.4.3's Emscripten WASM binary aborts during `PGlite.create()` with:
```
PGLite failed to initialize its WASM runtime. Aborted(). Build with -sASSERTIONS for more info.
```

Bun 1.3.14 + PGLite 0.4.3 on Linux 6.14.0 does NOT have this issue, so the crash is kernel-specific. The `@electric-sql/pglite/vector` subpath import also fails in bun's global install for 0.4.3 (exports map exists but bun can't resolve subpath from global cache).

**Fix — upgrade PGLite to 0.5.4 via npm and graft into bun's global cache:**

```bash
# 1. Create a stable npm-installed version (npm handles subpath exports properly)
mkdir -p ~/.gbrain-pglite
cd ~/.gbrain-pglite
npm init -y
npm install @electric-sql/pglite@0.5.4

# 2. Verify the vector extension is present
ls node_modules/@electric-sql/pglite/vector/     # Should show index.js, index.d.ts
ls node_modules/@electric-sql/pglite/contrib/pg_texample/  # Should show index.js, index.d.ts

# 3. Replace bun's global cache PGLite with npm's install
rm -rf ~/.bun/install/global/node_modules/@electric-sql/pglite
cp -r ~/.gbrain-pglite/node_modules/@electric-sql/pglite \
  ~/.bun/install/global/node_modules/@electric-sql/pglite
```

**Why npm works where bun fails:** npm's install creates a complete `node_modules/` tree inside PGLite's own directory with proper `package.json` files for subpath exports. Bun's global install flattens the tree and the subpath resolution fails for `@electric-sql/pglite/vector` and `@electric-sql/pglite/contrib/pg_texample`.

### PGLite WASM crash on kernel 7.0 — autopilot restart-loop wrapper

On kernel 7.0 (Linux Mint 22.3 Zena), the PGLite 0.4.3 WASM shipped with gbrain v0.42.52.0
crashes with an unhandled promise rejection:
```
[unhandledRejection] WebAssembly.Module doesn't parse at byte 4201158:
parsing ended before the end of Code section
```
Even after swapping in PGLite 0.5.4's WASM, a secondary error surfaces:
```
[unhandledRejection] Table import env:__indirect_function_table provided an
'initial' that is too small
```
This is a **bun + PGLite compatibility issue on kernel 7.0** — the v0.4.3 WASM
was compiled with an Emscripten version whose ABI is incompatible with bun's
WASM runtime on this kernel. The v0.5.4 WASM uses a different layout that triggers
a separate WASM table-size error.

**Critical insight: the autopilot cycle still completes successfully.** All phases
(sync, embed, consolidate, patterns, purge) run to completion. The crash is a
benign unhandled rejection during WASM module teardown after the cycle finishes.
The process exits with code 1, systemd restarts it, and the cycle runs again.

```bash
# autopilot.err will show the cycle completing then crashing:
[cycle.sync] done
[...all phases done...]
[cycle] score=45 elapsed=2s next=150s
[unhandledRejection] WebAssembly.Module doesn't parse at byte 4201158: ...
```

**Fix — autopilot wrapper script with restart loop:**

Replace the `exec`-based autopilot-run.sh with a `while true` loop so the process
restarts after each benign crash:

```bash
#!/bin/bash
# ~/.gbrain/autopilot-run.sh
[ -f ~/.zshenv ] && source ~/.zshenv 2>/dev/null
source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null || true

# PGLite WASM throws a benign unhandled rejection on kernel 7.0. The cycle
# completes successfully but the rejection crashes the process. Restart cleanly.
while true; do
  ~/.local/bin/gbrain autopilot --repo '~/brain/moses'
  echo "[wrapper] autopilot exited with $?, restarting in 5s..."
  sleep 5
done
```

Also reduce systemd's `RestartSec` to minimize downtime between restarts:

```ini
# ~/.config/systemd/user/gbrain-autopilot.service
RestartSec=5
```

Then reload and restart:
```bash
systemctl --user daemon-reload
systemctl --user restart gbrain-autopilot
systemctl --user status gbrain-autopilot  # verify 'active (running)'
```

**Diagnosis checklist:**
1. `systemctl --user status gbrain-autopilot` — shows auto-restart loop
2. `journalctl --user -u gbrain-autopilot -n 20` — repeatedly exited code 1
3. `tail ~/.gbrain/autopilot.err | grep -i "unhandled\|error\|rejection"` — confirms it's the WASM error
4. `tail ~/.gbrain/autopilot.log` — verify the cycle actually completed before crash
5. `~/.local/bin/gbrain doctor` — directly reproduces the WASM error

If the autopilot cycle itself is failing (not just the post-cycle teardown), use the
PGLite 0.5.4 npm upgrade from the previous section instead.

## Pitfalls

- **Wrong repo path on install.** Autopilot's default repo path may be a macOS path (`/Users/luke/brain/moses`). On Linux, the correct path is `/home/<user>/brain/<agent-name>`. Always pass `--repo <absolute-path>` during install. To fix after the fact: `gbrain autopilot --uninstall && gbrain autopilot --install --repo <correct-path>`.
- **Autopilot and crons are independent.** If you have a cron that also does `gbrain sync`, remove it — autopilot and the cron will conflict (both trying to sync the same file at the same time, causing lock contention on the PGLite database).
- **PGLite is single-writer.** Stop autopilot before large sync or dream operations. Autopilot handles internal sync fine, but any CLI command that needs DB access (`gbrain dream`, `gbrain sync`, `gbrain stats`, `gbrain sources list`) will hang or fail with a WASM error while autopilot holds the lock.
- **PGLite lock blocks CLI commands while autopilot runs.** While the autopilot daemon is active, commands like `gbrain list` and `gbrain get` will hang indefinitely (`Timed out waiting for PGLite lock`). This is **by design** — the autopilot holds the database exclusively. The PID `-42` in `postmaster.pid` is normal for PGLite embedded mode, not a crash. To run CLI commands: stop the autopilot, run your command, then restart it.
- **gbrain commands can be slow** (10-30s). The autopilot daemon runs the `dream` cycle at night — the actual maintenance is async. The creative cron just needs to query, not maintain.
- **Embedding timeouts without GBRAIN_AI_EMBED_TIMEOUT_MS.** The default embed timeout is low. Add `Environment=GBRAIN_AI_EMBED_TIMEOUT_MS=300000` to the systemd service file (`~/.config/systemd/user/gbrain-autopilot.service`), then `systemctl --user daemon-reload && systemctl --user restart gbrain-autopilot.service`.
- **Autopilot must run under systemd, not as a raw bun process.** The gbrain-wrapper.sh and watchdog both expect a systemd service (uses `systemctl --user`). If started as a bare background bun process, the watchdog reports DEGRADED and wrapper lifecycle silently fails. Always use `systemctl --user {start|stop|restart} gbrain-autopilot.service`.
- **Stale `database_url` in config causes `sources list` timeout.** `gbrain sources list` connects to the URL in `~/.gbrain/config.json` (default timeout 10s). If that URL points to a Postgres that isn't running, every CLI command hangs and eventually times out, triggering `gbrain_sources_ok` health alerts. **Fix:** remove `database_url` from config when using PGLite engine — the `database_path` is sufficient. Backup first, then: `python3 -c "import json, os; c=json.load(open(os.path.expanduser('~/.gbrain/config.json'))); del c['database_url']; json.dump(c, open(os.path.expanduser('~/.gbrain/config.json'), 'w'), indent=4))"`

## Stop/Dream/Restart Pattern (Linux, systemd)

On Linux (this server), the autopilot runs as a systemd user service
(`gbrain-autopilot.service`). Any cron job that needs exclusive DB access
(e.g., `gbrain dream`) must stop the autopilot first and restart afterward.

**Two critical gotchas discovered in production:**
- **Stale lock files.** After killing the autopilot, three lock files persist
  and block `gbrain dream` with "another cycle is already running":
  `autopilot.lock`, `cycle.lock`, and PGLite's `.gbrain-lock/lock`. The script
  clears all three.
- **Database stale cycle state.** Even after clearing file locks, `gbrain dream`
  may report "locked" because PGLite's database still tracks the interrupted
  cycle. Fix: run `gbrain dream --phase purge` before the full dream.

The canonical implementation is in `~/.hermes/scripts/gbrain-nightly-dream.sh` and
`~/.hermes/scripts/gbrain-wrapper.sh` — both use `systemctl --user` for lifecycle:

```bash
#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000   # Per-call embed timeout (env-overridable)
WRAPPER="$HOME/.hermes/scripts/gbrain-wrapper.sh"

# ── Step 1: Stop autopilot via systemd ───────────────────────
systemctl --user stop gbrain-autopilot.service
sleep 1

# ── Step 1b: Clear stale lock files ──────────────────────────
for lock in "$HOME/.gbrain/autopilot.lock" "$HOME/.gbrain/cycle.lock" \
            "$HOME/.gbrain/brain.pglite/.gbrain-lock/lock" "$HOME/.gbrain/.locks"; do
    [ -e "$lock" ] && rm -rf "$lock"
done

# ── Step 2: Run the DB-dependent command via wrapper ─────────
"$WRAPPER" dream 2>&1 | tail -20

# ── Step 3: Restart autopilot via systemd ────────────────────
systemctl --user start gbrain-autopilot.service
```

> **Always use `systemctl --user` to manage the autopilot lifecycle.**
> Never start the autopilot as a raw `bun` background process — the gbrain-wrapper.sh
> and watchdog both expect a systemd service.

### Key Environment Variables

| Var | Default | Override | Purpose |
|-----|---------|----------|---------|
| `GBRAIN_REPO` | Auto-detect from autopilot → `~/brain/moses` | `GBRAIN_REPO=/path/to/brain` | Brain repo path for restarting autopilot |
| `DREAM_TIMEOUT` | `300` | `DREAM_TIMEOUT=600` | Max seconds for the full dream command |
| `GBRAIN_AI_EMBED_TIMEOUT_MS` | `300000` (5 min) | export before script | Per-call embed timeout (gbrain internal) |

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **systemd service for autopilot** | Single canonical lifecycle — gbrain-wrapper.sh, watchdog, and cron scripts all use `systemctl --user`. No orphan bun processes. |
| **`GBRAIN_AI_EMBED_TIMEOUT_MS` via systemd Environment=** | Prevents embedding timeouts on large pages (5 min per-call). Set once in the service file, applies to all cycles. |
| **Stop autopilot first for CLI commands** | PGLite is single-writer — the autopilot holds the exclusive lock. Stop via `systemctl --user stop`, run CLI, restart. |
| **Lock file cleanup** | autopilot.lock + cycle.lock + PGLite's .gbrain-lock all persist after process death |
| **Pre-flight `dream --phase purge`** | Clears database-level stale cycle state that file-lock cleanup misses |
| **`timeout` wrapper on dream** | Prevents runaway embedding from locking the system indefinitely |
| **tail -20 on output** | Follows cron truncation convention — full output would be wasteful |

### Pitfalls (Added in Production)

- **Hardcoded repo path will break on other machines.** The original script had
  `GBRAIN_REPO="~/brain/moses"`. Other agents have different usernames
  and brain paths. Always auto-detect from the running autopilot's `--repo` flag.
- **Missing embed timeout can lock the script.** The embed phase processes 142+
  orphan pages. Without a `DREAM_TIMEOUT`, a slow embedding run can hang the cron
  indefinitely. Set both `GBRAIN_AI_EMBED_TIMEOUT_MS` (per-call) and a
  `timeout` (whole command).
- **Lock files persist after kill.** Three separate lock files survive the
  autopilot process death. Clearing just `autopilot.lock` is not enough — you
  must also clear `cycle.lock` and PGLite's `.gbrain-lock/lock`.
- **Pre-flight purge is essential.** Even with all file locks cleared, PGLite's
  database may still track an interrupted dream cycle. Run
  `gbrain dream --phase purge` first — it takes < 0.1s and prevents the "locked" error.

### Commands That Require the Lock

These fail silently (WASM error) while autopilot runs — always stop first:
- `gbrain dream` — full pipeline (sync, embed, synthesize, patterns, consolidate)
- `gbrain sync` — manual sync cycle
- `gbrain stats` — database statistics
- `gbrain sources list` — reads registered sources from DB

### Commands Safe to Run With Autopilot

These do NOT need DB access and run alongside autopilot:
- `gbrain doctor --fast` — filesystem-only checks
- `gbrain check-update` — network check, no DB
- `gbrain upgrade` — binary self-update, no DB
- `gbrain list -n 20` — reads from cache, not DB (only the creative cron needs this)

## Related skills

- `cron-quality-gate` — adds self-check + watchdog to prevent cron output gibberish
- `cron-job-management` — naming conventions, drift guard, prompt design for all crons