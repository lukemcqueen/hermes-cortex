---
name: hermes-backup
description: "Use when performing a full-system backup of a Hermes Agent server — survey, clean up caches, checkpoint databases, bundle repos and configs, compress, and write a manifest. Pairs with hermes-recovery for the restore side."
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [backup, maintenance, devops, hermes, recovery]
    related_skills: [hermes-recovery, weekly-auto-fix]
---

# Hermes Agent Full-System Backup

Systematic procedure to create a complete, verifiable backup of a Hermes Agent server. Covers repo bundles, session databases, knowledge stores (gbrain PGlite), Hermes configuration (skills/scripts/plugins/cron), brain sources, langfuse stack config, docker image archives, nginx config, shell config, and credentials.

## When to Use

- **Full-system backup** — user asks "backup everything" or "backup the server"
- **Pre-migration snapshot** — before a server move, OS upgrade, or hardware swap
- **Disaster recovery prep** — create a restore point for use with `hermes-recovery`
- **Periodic maintenance** — scheduled weekly/monthly full backup

**Don't use for:** single-file backups, git-only backups (use `git bundle` directly), database-only dumps (use sqlite3/pg_dump directly).

## Workflow Order

Always run in this sequence — later steps depend on earlier data:

### 1. Survey

Start by understanding the terrain. Run these checks and log the results:

```
df -h /
du -sh ~/* ~/.[!.]* 2>/dev/null | sort -rh | head -30
du -sh ~/.hermes/
ls -la ~/.hermes/state.db ~/.hermes/kanban.db ~/.hermes/web-cache/cache.db
ls ~/.hermes/*.json ~/.hermes/*.yaml 2>/dev/null
for repo in ~/hermes-cortex ~/.hermes/hermes-agent; do
  if [ -d "$repo" ]; then
    git -C $repo log --oneline -1 2>/dev/null
    git -C $repo gc --auto 2>/dev/null
  fi
done
docker ps --format "{{.Names}} {{.Status}}" 2>/dev/null
du -sh ~/brain/ ~/.brain/ ~/.gbrain/ ~/langfuse/ 2>/dev/null
```

**Completion criteria:** You have a tree of what exists and its sizes.

### 2. Pre-Backup Cleanup

Remove package manager caches, browser binaries, and build artifacts. These are re-downloadable and inflate backup size.

**Safe to remove:**
- `~/.npm/_cacache` — npm cache
- `~/.bun/install/cache` — bun install cache
- `~/.cache/ms-playwright` — Playwright browser binaries (646 MB typical)
- `~/.cache/electron` — Electron cache
- `~/.cache/mozilla` — Firefox cache
- `~/.cache/node-gyp` — C++ build artifacts
- `~/.cache/pip` — pip download cache
- `~/.cache/uv` — uv package cache
- `~/.cache/Homebrew` — Homebrew download cache
- `~/.zcompdump*` — zsh completions

```bash
rm -rf ~/.npm/_cacache ~/.bun/install/cache
rm -rf ~/.cache/ms-playwright ~/.cache/electron ~/.cache/mozilla
rm -rf ~/.cache/node-gyp ~/.cache/pip ~/.cache/uv ~/.cache/Homebrew
rm -f ~/.zcompdump*
```

**Do NOT remove:**
- `~/.hermes/` — Hermes runtime, skills, cron, sessions, config
- `~/.ollama/` — LLM models
- `~/.local/` — installed packages and binaries
- `~/.config/` — system configs
- `~/.gbrain/` — knowledge graph database
- `~/brain/`, `~/.brain/` — knowledge sources
- `~/langfuse/` — Langfuse stack config
- `~/hermes-cortex*` — git repos

**Skip from backup (re-downloadable):**
- Ollama models (~262 MB for nomic-embed-text) — `ollama pull` restores
- Python packages at `~/.local/lib/` (~2.1 GB) — restorable via pip/uv
- Hermes Agent node_modules + venv (~2.4 GB) — reconstructed from git bundle
- Langfuse Docker volumes — Postgres/ClickHouse data (live containers)

**Completion criteria:** At least 500 MB reclaimed. Report space saved.

### 3. Checkpoint SQLite Databases

Flush WAL files for consistent DB copies:

```bash
sqlite3 ~/.hermes/state.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 ~/.hermes/kanban.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 ~/.hermes/web-cache/cache.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

**Completion criteria:** `state.db-wal` and `state.db-shm` are 0 bytes or gone.

### 4. Create Backup Directory

```bash
BACKUP_DATE=$(date +%Y-%m-%d)
mkdir -p ~/backups/$BACKUP_DATE/{databases,configs,brain,langfuse,docker-images,repos}
```

### 5. Bundle Git Repositories

Use `git bundle` for portable full-repo snapshots (all branches, all tags):

```bash
cd ~/hermes-cortex && git bundle create ~/backups/$BACKUP_DATE/repos/hermes-cortex-public.bundle --all
# ~/hermes-cortex-private no longer a git repo — backup via cp -r ~/hermes-cortex-private ~/backups/$BACKUP_DATE/private-data/
cd ~/.hermes/hermes-agent && git bundle create ~/backups/$BACKUP_DATE/repos/hermes-agent.bundle --all
```

**Do NOT back up** `node_modules/`, `venv/`, or build artifacts — the bundle captures only git-tracked objects. The full checkout is reconstructed from the bundle.

**Restore:** `git clone hermes-*.bundle <dirname>`

**Completion criteria:** All bundle files exist and have non-zero size.

### 6. Copy Databases

```bash
cp ~/.hermes/state.db ~/backups/$BACKUP_DATE/databases/
cp ~/.hermes/kanban.db ~/backups/$BACKUP_DATE/databases/
cp ~/.hermes/web-cache/cache.db ~/backups/$BACKUP_DATE/databases/
```

**gbrain PGlite** — PostgreSQL data directory, copy the full tree:

```bash
mkdir -p ~/backups/$BACKUP_DATE/databases/gbrain
cp -a ~/.gbrain/brain.pglite ~/backups/$BACKUP_DATE/databases/gbrain/
cp ~/.gbrain/preferences.json ~/backups/$BACKUP_DATE/databases/gbrain/
cp ~/.gbrain/config.json ~/backups/$BACKUP_DATE/databases/gbrain/
```

**Completion criteria:** All DB files in place matching original sizes.

### 7. Copy Hermes Configuration

Core config:
```bash
cp ~/.hermes/config.yaml ~/backups/$BACKUP_DATE/configs/
cp -a ~/.hermes/skills ~/backups/$BACKUP_DATE/configs/
cp -a ~/.hermes/scripts ~/backups/$BACKUP_DATE/configs/
cp -a ~/.hermes/plugins ~/backups/$BACKUP_DATE/configs/ 2>/dev/null
cp -a ~/.hermes/cron ~/backups/$BACKUP_DATE/configs/
```

Root-level JSON state files:
```bash
mkdir -p ~/backups/$BACKUP_DATE/configs/hermes-root
for f in auth.json gateway_state.json channel_directory.json \
         docker-daemon.json processes.json \
         provider_models_cache.json ollama_cloud_models_cache.json; do
  cp ~/.hermes/$f ~/backups/$BACKUP_DATE/configs/hermes-root/ 2>/dev/null
done
cp ~/.hermes/models_dev_cache.json ~/backups/$BACKUP_DATE/configs/ 2>/dev/null
```

Hermes subdirectories (dashboard, LSP, offline scripts):
```bash
mkdir -p ~/backups/$BACKUP_DATE/configs/hermes-subdirs
cp -a ~/.hermes/dashboard ~/backups/$BACKUP_DATE/configs/hermes-subdirs/ 2>/dev/null
cp -a ~/.hermes/lsp ~/backups/$BACKUP_DATE/configs/hermes-subdirs/ 2>/dev/null
cp -a ~/.hermes/offline ~/backups/$BACKUP_DATE/configs/hermes-subdirs/ 2>/dev/null
```

System configs:
```bash
cp -a ~/.hermes/cache ~/backups/$BACKUP_DATE/configs/ 2>/dev/null
cp -a ~/.hermes/bin ~/backups/$BACKUP_DATE/configs/ 2>/dev/null
cp ~/.zshrc ~/backups/$BACKUP_DATE/configs/.zshrc
crontab -l > ~/backups/$BACKUP_DATE/configs/crontab.txt 2>/dev/null
cp ~/.git-credentials ~/backups/$BACKUP_DATE/configs/ 2>/dev/null
```

Nginx config (try without sudo first):
```bash
cp /etc/nginx/sites-enabled/hermes-services.conf ~/backups/$BACKUP_DATE/configs/nginx-hermes-services.conf 2>/dev/null
```

**Completion criteria:** Every config directory has files matching the source.

### 8. Copy Brain and Knowledge Data

```bash
cp -a ~/brain ~/backups/$BACKUP_DATE/brain/brain
cp -a ~/.brain ~/backups/$BACKUP_DATE/brain/dot-brain
```

**Completion criteria:** Both brain dirs present at expected sizes.

### 9. Copy Langfuse and Docker Images

```bash
mkdir -p ~/backups/$BACKUP_DATE/langfuse ~/backups/$BACKUP_DATE/docker-images
cp ~/langfuse/docker-compose.yml ~/backups/$BACKUP_DATE/langfuse/
cp ~/langfuse/.env ~/backups/$BACKUP_DATE/langfuse/
cp ~/.hermes/docker-*.tar.gz ~/backups/$BACKUP_DATE/docker-images/ 2>/dev/null
```

**Completion criteria:** Langfuse configs and any docker image archives present.

### 10. Write Manifest

Create `MANIFEST.txt` inside the backup directory. Include:
- Date, hostname
- Category breakdown with file counts and sizes
- What was cleaned up (space reclaimed)
- What was intentionally skipped (Ollama models, Python packages, docker volumes)
- How to restore

**Completion criteria:** MANIFEST.txt exists, all backup files accounted for.

### 11. Compress the Archive

```bash
cd ~/backups
tar czf $BACKUP_DATE-hermes-backup.tar.gz $BACKUP_DATE/
```

Verify: `tar tzf $BACKUP_DATE-hermes-backup.tar.gz | head -5`

Log compression ratio (raw vs compressed size).

### 12. Record in Memory

Save the backup date, archive path, and size to memory so future sessions can find it.

**Completion criteria:** Memory updated with backup location.

## Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **state.db copied while gateway is writing** | WAL not flushed, partial write | Checkpoint first (`PRAGMA wal_checkpoint(TRUNCATE)`), then copy |
| **git bundle from dirty working tree** | Uncommitted changes excluded from bundle | `git status --short` first — report dirty state; bundle anyway for now |
| **~/.git-credentials zeroed by gateway write protection** | File exists but 0 bytes | Check with `wc -c` after copy; re-populate if zeroed |
| **Nginx config permission denied** | Can't read `/etc/nginx/sites-enabled/*` | Try without sudo; if blocked, skip and note in manifest |
| **gbrain PGlite has lock files** | Copy errors on `.gbrain-lock/lock` | Skip lock files — they're recreated on restart |
| **Multiple backup dirs same day** | Previous backup at same date path | Use `$BACKUP_DATE-v2` suffix |
| **Docker images NOT pre-exported** | No `~/.hermes/docker-*.tar.gz` | Skip step; note in manifest that images must pull from registry |
| **Backup archive too large for disk** | `df -h` shows < 1 GB free | Survey first; skip re-downloadable items aggressively |

## Verification Checklist

- [ ] Survey complete — disk space, repo state, docker status all known
- [ ] Cleanup freed ≥ 500 MB (or justified as minimal)
- [ ] SQLite databases checkpointed (WAL files zeroed)
- [ ] All 3 git repos bundled (public, private, hermes-agent)
- [ ] state.db, kanban.db, web-cache.db, gbrain PGlite all copied
- [ ] config.yaml, skills/, scripts/, cron/, plugins/ all backed up
- [ ] Root JSON files (auth, gateway, channel, processes, caches) backed up
- [ ] Hermes subdirs (dashboard, LSP, offline) backed up
- [ ] ~/brain/ and ~/.brain/ both copied
- [ ] nginx config copied (or skipped with reason in manifest)
- [ ] .zshrc, crontab.txt, .git-credentials backed up
- [ ] Langfuse config copied
- [ ] Docker image archives copied (or noted absent)
- [ ] MANIFEST.txt written — covers all included and excluded items
- [ ] Archive compressed — verified with `tar tzf`
- [ ] Final archive size ≤ 1 GB (or justified larger)
- [ ] Backup location recorded in memory for future recovery