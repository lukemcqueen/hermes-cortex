# Symlink Policy — Hermes Cortex ↔ Hermes Agent

## Why This Exists

Hermes Cortex deploys runtime files (scripts, skills, state, data) to
`~/.hermes-cortex/`. Hermes Agent reads its runtime files from `~/.hermes/`.
To keep both working without duplicating files, Cortex directories that Hermes
Agent needs to find at `~/.hermes/` are **symlinked** from `~/.hermes-cortex/`.

This document tells every agent which directories are symlinked and why,
and what to do when installing or updating.

---

## 🔴 DO NOT TOUCH — Hermes Agent Core

These are managed by Hermes Agent itself and must remain as real directories
or files at `~/.hermes/`. **Never replace these with symlinks to
`~/.hermes-cortex/`.**

| Path | Purpose | Why not symlink |
|------|---------|----------------|
| `config.yaml` | Hermes Agent configuration | Hermes Agent reads this at startup |
| `.env` | Hermes Agent environment variables | Managed by Hermes setup |
| `profiles/` | Agent profiles (per-device config) | Hermes Agent manages profiles |
| `plugins/` | Agent plugins | Plugin loader resolves from here |
| `SOUL.md` | Agent identity document | Per-agent, managed by soul-refinement cron |
| `state.db` (+ -shm, -wal) | **4.5GB conversation database** | Hermes Agent's session/state DB |
| `cron/` | Cron job definitions | Hermes cron scheduler reads from here |
| `cron.db` | Cron scheduler database | Hermes cron scheduler owns this |
| `hermes-agent/` (1.1GB) | Hermes Agent install itself | The entire agent runtime |
| `lsp/` (140M) | Language servers for TUI | Hermes TUI uses these |
| `bin/` | CLI tools (tirith, uv, uvx) | Hermes Agent's binary tools |
| `bin/` symlinks to `offline/` | CLI shortcuts to offline tools | Point through the offline/ symlink |
| `auth.json` | Authentication tokens | Hermes Agent auth |
| `logs/` | Logs | Hermes Agent writes logs here |
| `cache/` | Hermes Agent caches | Caches managed by Hermes |
| `checkpoints/` | Session checkpoints | Hermes Agent session management |
| `kanban/` + `kanban.db` | Kanban board state | Hermes kanban tool |
| `gateway.*` | Gateway state | Hermes gateway process |
| `nginx/` | nginx config for Hermes gateway | Hermes gateway setup |
| `templates/` | Template files | Hermes template system |
| `repos.yaml` | Repo configuration | Hermes repo management |
| `platforms/` | Platform connection configs | Hermes messaging platforms |
| `pets/` | Petdex mascots | Hermes pet system |
| `mcp-venv/` | MCP Python virtualenv | Hermes MCP system |
| `audio_cache/`, `image_cache/`, `images/` | Media caches | Hermes media caching |
| Various `.json` cache files | Model/provider caches | Hermes model discovery |
| `agent-bus.conf`, `hermes-inbox.conf` | Agent Bus auth credentials (legacy) | Hermes inbox client auth |
| `agent-name` | Agent identity name | Hermes agent identification |

**Also DO NOT touch these in `~/.hermes-cortex/`:**
- `~/.hermes-cortex/skills/` — Must be a **symlink to `~/.hermes/skills/`** (not a real directory). Hermes Agent's `skills_sync.py` manages `~/.hermes/skills/` as the canonical skill store. `cortex-update.sh` deploys Cortex skills to `~/.hermes-cortex/skills/` which resolves through the symlink to ~/.hermes/skills/.

---

## ✅ Symlinked — Cortex Runtime

These are real directories at `~/.hermes-cortex/` with symlinks at `~/.hermes/`.
Symlinks work because macOS/Linux resolve writes through the symlink
transparently — no data is lost.

### Read-only content (deployed by cortex-update.sh)

| Symlink | Content | Managed by | Size |
|---------|---------|------------|------|
| `scripts/` | All agent scripts | `cortex-update.sh register()` | — |
| `offline/` | Code corpus + tools | `cortex-update.sh sync_code_corpus()` | 3.3M |
| `memory/` | Agent pointer memory | Agent memory tool | 4K |
| `memories/` | MEMORY.md, USER.md | Agent session writes | 8K |
| `hooks/` | Git pre-commit/pre-push hooks | `install-score-hook.sh` | 16K |
| `mcp-servers/` | MCP server scripts | `cortex-update.sh register()` | 32M |

### Runtime state (writes resolve through symlink)

| Symlink | Content | Managed by | Size |
|---------|---------|------------|------|
| `state/` | Health, inbox, update tracking | Cortex crons + scripts | 352K |
| `data/` | Loop governance DB, session embeddings | loop-governance system | 7.5M |
| `sessions/` | Session history archive | update-session-state.sh | 58M |
| `dashboard/` | Cortex dashboard app | Dashboard server | 12M |
| `health-server/` | Health vector server | health-vector.py | 504K |
| `web-cache/` | Web cache for offline knowledge | web_cache.py | 20M |

### Individual file symlinks

| Symlink | Content | Managed by |
|---------|---------|------------|
| `bible-reading-tracker.json` | Daily Bible reading state | agent-daily-bible-reading.py |
| `titus-avatar.html` | Titus avatar HTML | Titus profile |
| `evals/` | Evaluation data (empty) | (future use) |

---

## Directory Map

```
~/.hermes/                          ~/.hermes-cortex/
├── config.yaml           [REAL]    ├── scripts/          [REAL]
├── .env                  [REAL]    ├── tools/            [REAL]
├── profiles/             [REAL]    ├── sessions/         [REAL]
├── plugins/              [REAL]    ├── state/            [REAL]
├── SOUL.md               [REAL]    ├── data/             [REAL]
├── state.db              [REAL]    ├── offline/          [REAL]
├── cron/                 [REAL]    ├── memory/           [REAL]
├── hermes-agent/         [REAL]    ├── memories/         [REAL]
├── auth.json             [REAL]    ├── web-cache/        [REAL]
├── logs/                 [REAL]    ├── dashboard/        [REAL]
├── cache/                [REAL]    ├── health-server/    [REAL]
├── sessions/             [REAL]    ├── mcp-servers/      [REAL]
├── data/                 [REAL]    ├── evals/            [REAL]
├── ... (Hermes runtime)            ├── certs/            [REAL]
│                                   ├── agent-bus/      [REAL]
│                                   ├── bin/              [REAL]
├── scripts → .hermes-cortex/       │
│  .env                  [REAL]     │
│  (Each .env is independent —     ├── skills → ../.hermes/skills/ [SYMLINK]
│   NOT symlinked.                  │
│   ~/.hermes/.env = Agent only    Both point to same skills dir
│   ~/.hermes-cortex/.env = Cortex (Hermes manages ~/.hermes/skills/
│   ~/hermes-cortex/.env = Repo)   via skills_sync.py, cortex-update
│                                   deploys through the symlink)
```

---

## Why Symlinks Work

Symlinks work on all Hermes Agent platforms (macOS, Linux, Ubuntu) for all
filesystem operations: **read, write, append, open, stat, rename** (on the
link, not the target), and **delete** (on the link, not the target). Writes
to `~/.hermes/<dir>/file` transparently go to `~/.hermes-cortex/<dir>/file`.

The exception is container/CI environments with `--read-only` root filesystems
— but those don't use `~/.hermes/` as a writable directory anyway.

## When to Symlink vs When to Copy

| Situation | Approach |
|-----------|----------|
| Directory is read-only after deployment | **Symlink** — saves disk space, single source of truth |
| Directory has runtime writes | **Symlink** — writes resolve through the link to the real path |
| File must be at `~/.hermes/` for Hermes Agent to find it | **Symlink** — if Hermes can follow symlinks (it can) |
| File is a Hermes Agent core config | **Real file** — never symlink |
| The deployment target is already `~/.hermes-cortex/` | **Symlink** — cortex-update writes to the real path |

## Installation / Update

### Created during initial setup

The symlinks below are created once during `install.sh` or `cortex-setup.sh`.
`cortex-update.sh` does NOT manage them — it only deploys content.

### What to do if a symlink breaks

```bash
# Verify
ls -la ~/.hermes/scripts
# → broken symlink

# Re-create
rm ~/.hermes/scripts
ln -s ~/.hermes-cortex/scripts ~/.hermes/scripts
```

### Fresh install: create all symlinks

```bash
# Cortex dirs → symlink from ~/.hermes/
for dir in scripts offline state data sessions memory memories \
           hooks mcp-servers dashboard health-server web-cache evals; do
  if [ -d ~/.hermes/$dir ] && [ ! -L ~/.hermes/$dir ]; then
    rm -rf ~/.hermes/$dir
    ln -s ~/.hermes-cortex/$dir ~/.hermes/$dir
  fi
done

# Individual files
for f in bible-reading-tracker.json titus-avatar.html; do
  if [ -f ~/.hermes/$f ] && [ ! -L ~/.hermes/$f ]; then
    cp ~/.hermes/$f ~/.hermes-cortex/$f
    rm ~/.hermes/$f
    ln -s ~/.hermes-cortex/$f ~/.hermes/$f
  fi
done

# CRITICAL: skills must be a REAL directory at ~/.hermes/, NOT a symlink
# ~/.hermes-cortex/skills/ must be a symlink TO ~/.hermes/skills/
if [ -d ~/.hermes-cortex/skills ] && [ ! -L ~/.hermes-cortex/skills ]; then
  rm -rf ~/.hermes-cortex/skills
  ln -s ~/.hermes/skills ~/.hermes-cortex/skills
fi
```

## Verification

```bash
# List all symlinks in ~/.hermes/ and verify they resolve
find ~/.hermes -maxdepth 1 -type l | while read link; do
  target=$(readlink "$link")
  if [ -e "$target" ]; then echo "✅ $(basename $link)";
  else echo "❌ BROKEN: $(basename $link)"; fi
done

# Verify ~/.hermes-cortex/skills is a symlink TO ~/.hermes/skills/
ls -la ~/.hermes-cortex/skills
# → lrwxr-xr-x ... skills -> /Users/luke/.hermes/skills
```

## Audit Trail

| Date | Action | By |
|------|--------|-----|
| 2026-07-07 | Initial policy created | Titus |
| 2026-07-07 | Migrated 15 dirs + 2 files from ~/.hermes/ to ~/.hermes-cortex/ with symlinks | Titus |
|| 2026-07-07 | Identified skills/ as Hermes Agent canonical dir — reverted symlink direction | Titus |
|| 2026-07-08 | Stripped aspirational symlinks from doc — only scripts/ is actually symlinked. .env split into 3 independent files. | Moses |
