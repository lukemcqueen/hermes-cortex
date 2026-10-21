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
| `.env`, `.env` | Agent Bus auth credentials (legacy) | Hermes inbox client auth |
| `agent-name` | Agent identity name | Hermes agent identification |

**Also DO NOT touch these in `~/.hermes-cortex/`:**
- `~/.hermes-cortex/skills/` — Must be a **REAL directory**: Cortex OWNS the skill library.
  `~/.hermes/skills/` must be a **symlink to it** (not a real directory). This is the REVERSE
  of the 2026-07-07 direction, deliberately (2026-10-21): the fleet is moving OFF the Hermes
  agent, so Cortex must own the canonical store instead of borrowing the tree that Hermes
  Agent's `skills_sync.py` manages. `cortex-update.sh` deploys the skills into the real cortex
  tree, then publishes the agent-visible view at `~/.agents/skills/` (the cross-client standard
  path read natively by Codex, Cursor, Copilot, OpenCode and Antigravity), so every harness
  reads the same bytes through a pointer. Invert per host with
  `ops/scripts/manage/migrate-skills-ownership.py` — it moves the real tree, links back, and
  verifies; it never deletes a tree.

**Omarchy desktop coexistence (moses, 2026-10-21).** On a host running the Omarchy desktop,
omarchy links its own agent skills (`omarchy`, `diagnose-crash`) into `~/.agents/skills` as a
**real directory** — the same path the cortex publisher wants as its pointer. The two coexist
cleanly because omarchy's skills are **already symlinked inside the cortex defaults tree**
(`~/.hermes-cortex/skills/omarchy` → `/usr/share/omarchy/default/agents/skills/omarchy`), so
publishing the pointer exposes both omarchy's skills AND the full cortex library through one
path. The publish tool (`publish-agent-skills.py`) refuses to clobber a foreign real dir by
design (exit 4, "DECISION REQUIRED") — the operator runs `--adopt-published`, which **preserves
the occupied tree by rename** to `~/.agents/skills.pre-publish-<stamp>` (nothing deleted) and
replaces it with the pointer. Omarchy's own migration scripts that created the real dir are
marked applied (`~/.local/state/omarchy/migrations/`), so they do not re-run and re-occupy the
path on update; the omarchy crash-watch consumer reads its skill via the absolute
`/usr/share/omarchy/...` path, unaffected by the pointer change.

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
│                                   ├── cortex-bus/      [REAL]
│                                   ├── bin/              [REAL]
├── scripts → .hermes-cortex/       │
│  .env                  [REAL]     │
│  (Each .env is independent —     ├── skills → ../.hermes/skills/ [SYMLINK]
│   NOT symlinked.                  │
│   ~/.hermes/.env = Agent only    Both point to same skills dir
│   ~/hermes-cortex/.env = Cortex (Hermes manages ~/.hermes/skills/
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

# CRITICAL (inverted 2026-10-21): the skills tree must be a REAL directory in
# ~/.hermes-cortex/, and the ~/.hermes path a symlink TO it — Cortex owns the library.
# Do NOT do this by hand: the tool MOVES the real tree, links back, and verifies.
#   python3 ops/scripts/manage/migrate-skills-ownership.py --check
#   python3 ops/scripts/manage/migrate-skills-ownership.py
# It refuses to guess when BOTH paths are real directories (--adopt-borrower /
# --keep-borrower), preserves the non-winning tree by rename, and never deletes.
if [ -d ~/.hermes/skills ] && [ ! -L ~/.hermes/skills ]; then
  echo "⚠️  ~/.hermes/skills is still a real directory — ownership not inverted on this host"
  echo "    run: python3 ops/scripts/manage/migrate-skills-ownership.py"
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

# Verify the cortex tree is REAL and the harness paths POINT at it
ls -ld ~/.hermes-cortex/skills ~/.hermes/skills ~/.agents/skills
# → drwx------ ... ~/.hermes-cortex/skills             (real — cortex owns it)
# → ... ~/.hermes/skills -> ~/.hermes-cortex/skills    (Hermes pointer, transition)
# → ... ~/.agents/skills -> ~/.hermes-cortex/skills    (agent-visible standard path)
```

## Audit Trail

| Date | Action | By |
|------|--------|-----|
| 2026-07-07 | Initial policy created | Titus |
| 2026-07-07 | Migrated 15 dirs + 2 files from ~/.hermes/ to ~/.hermes-cortex/ with symlinks | Titus |
| 2026-07-07 | Identified skills/ as Hermes Agent canonical dir — reverted symlink direction | Titus |
| 2026-07-08 | Stripped aspirational symlinks from doc — only scripts/ is actually symlinked. .env split into 3 independent files. | Moses |
| 2026-10-21 | **INVERTED**: Cortex now owns the canonical skills tree — `~/.hermes-cortex/skills/` is a REAL directory, and `~/.hermes/skills` + `~/.agents/skills` are pointers to it. Reason: the fleet is moving off the Hermes agent, so the 2026-07-07 direction (Hermes canonical) had to be reversed. Tools: `ops/scripts/manage/migrate-skills-ownership.py` (invert, per host, verified, never deletes) and `ops/scripts/manage/publish-agent-skills.py` (publish the agent-visible view). | Esther |
| 2026-10-21 | **Omarchy coexistence**: on hosts running the Omarchy desktop, `~/.agents/skills` was omarchy's real dir (partial view). Published the cortex pointer with `--adopt-published` (preserves omarchy's tree by rename to `~/.agents/skills.pre-publish-<stamp>`, never deletes) — omarchy's skills were already symlinked inside the cortex defaults, so agents now see omarchy + all cortex skills via one pointer. | Moses |
