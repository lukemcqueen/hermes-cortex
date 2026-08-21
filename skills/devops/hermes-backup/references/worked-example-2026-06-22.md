# Worked Example — Full Backup 2026-06-22

This is a reference from the actual backup run on moses (Linux Mint 22, 109 GB /). Use it to calibrate expected sizes and structure for future runs.

## Pre-Backup Disk State

| Area | Size | Action |
|------|------|--------|
| `~/.hermes/` | 3.1 GB | Backed up selectively |
| `~/.local/` | 2.2 GB | Skipped (Python packages) |
| `~/.cache/` | 1.3 GB | Cleaned |
| `~/.bun/` | 578 MB | Cache cleaned (490 MB), bin/ kept |
| `~/.npm/` | 321 MB | Cache cleaned (304 MB) |
| `~/.ollama/` | 262 MB | Skipped (re-pullable) |
| `~/.legacy-brain/` | 90 MB | Backed up |
| `~/.config/` | 55 MB | Skipped (system configs) |
| `hermes-cortex-public` | 11 MB | Git bundle |
| `hermes-cortex-private` | 1.9 MB | Git bundle |
| `brain/` | 3.9 MB | Backed up |
| `langfuse/` | 16 KB | Backed up |
| **Total home** | **7.9 GB** | |

## Cleanup Results

| Cache | Size Removed |
|-------|-------------|
| Playwright browsers | 646 MB |
| bun install cache | 311 MB |
| npm cacache | 304 MB |
| uv cache | 219 MB |
| Electron cache | 110 MB |
| Mozilla cache | 92 MB |
| Homebrew cache | 79 MB |
| node-gyp cache | 65 MB |
| pip cache | 54 MB |
| **Total reclaimed** | **~1.9 GB** |

## Databases Checkpointed

- `state.db` — 102 MB (WAL: 272 KB → 0)
- `kanban.db` — 112 KB
- `web-cache/cache.db` — 32 KB

## Git Bundles

| Repo | Bundle Size |
|------|------------|
| hermes-cortex-public | 2.4 MB |
| hermes-cortex-private | 304 KB |
| hermes-agent (NousResearch) | 173 MB |

The hermes-agent source at `~/.hermes/hermes-agent/` is a 2.4 GB checkout (with node_modules, venv, etc.) but the git bundle captures only the 173 MB of tracked objects.

## Final Archive

- **Path:** `~/backups/2026-06-22-hermes-backup.tar.gz`
- **Raw size:** 976 MB
- **Compressed size:** 686 MB (70% compression ratio)
- **Host:** moses (Linux Mint 22)
- **Services running during backup:** Hermes gateway, dashboard (:8901), Langfuse stack (6 containers), Ollama

## Backup Composition (compressed)

| Category | Size | Contents |
|----------|------|----------|
| Git repos | 176 MB | 3 git bundles |
| Databases | 185 MB | state.db, kanban.db, cache.db, mycortex PGlite |
| Docker images | 415 MB | 4 pre-exported image tarballs |
| Hermes config | 89 MB | skills/, scripts/, cron/, config.yaml, dashboard, LSP, JSON state files, bin |
| Brain data | 17 MB | ~/brain/ + ~/.brain/ |
| Langfuse | small | docker-compose.yml + .env |
| System config | small | .zshrc, nginx conf, git-credentials |

## Post-Backup Disk

19 GB used / 84 GB free (was 21/83 before cleanup).

## Restore Notes

- All 3 bundles restore via `git clone <bundle> <dirname>`
- state.db goes to `~/.hermes/state.db`
- mycortex PGlite goes to `~/.legacy-brain/brain.pglite`
- Config dirs extract to `~/.hermes/` paths
- Brain data extracts to `~/brain/` and `~/.brain/`
- See `hermes-recovery` skill for the full restore workflow