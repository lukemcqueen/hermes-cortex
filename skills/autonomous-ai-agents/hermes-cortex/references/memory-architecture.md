# Hermes Cortex Memory Architecture

Six memory layers, from fastest/least durable to slowest/most durable:

```
Layer 1: Agent Prompt (MEMORY.md / USER.md)    — hot cache, lost on restart
Layer 2: Session State (.hermes-cortex/sessions/current.md) — this session only
Layer 3: Hermes Profile (~/.hermes/profiles/)   — agent identity, legacy isolation layer
Layer 4: Brain Source (~/brain/<source>/)        — cross-project deep knowledge (Mycortex)
Layer 5: Repo Memory (.hermes-cortex/memory/)    — per-project durable conventions
Layer 6: Repo Docs (docs/)                       — version controlled, team-visible
```

## How Knowledge Flows Across Projects (Uber-Agent Model)

The current model uses **one default Hermes profile** for all projects. Isolation is achieved entirely through mycortex source separation:

```
Session (default profile, working in Project A)
  |
  +-- MEMORY.md (shared — compact pointers only)
  +-- Consults ~/brain/default/ (federated — auto-searched, cross-project knowledge)
  +-- /brain project-a <query> → ~/brain/project-a/ (isolated, --source only)
  +-- /brain project-b <query> → ~/brain/project-b/ (isolated, --source only)
  +-- Writes learnings to ~/brain/default/ or ~/brain/<project>/ as appropriate
         |
         v
Next session (same default profile, working in Project B)
  +-- Same MEMORY.md (compact pointers remain valid)
  +-- Same brain/default (picks up cross-project learnings)
  +-- Queries project-b's isolated source independently
  +-- No memory bleed between projects — query isolation at mycortex level
```

## Two-Isolation-Axes Model (Current)

| Axis | What It Isolates | How It Shares |
|------|-----------------|---------------|
| **Brain Source (federated)** (`~/brain/default/`) | System recipes, cross-project knowledge | Auto-searched on every `/brain` query |
| **Brain Source (isolated)** (`~/brain/<project>/`) | Project-specific domain knowledge | Only searched with `--source <project>` — explicit opt-in |
| **Working directory** | File access | `cd <project> && hermes` → scoped to that repo's files |

## Brain Source vs Repo Memory

| Axis | Isolates | Shares | Access |
|------|----------|--------|--------|
| **Brain source** (`~/brain/<name>/`) | Nothing | Knowledge by topic | `/brain <source> <query>` |
| **Repo memory/** (`<project>/.hermes-cortex/memory/`) | Per-project truth | Per-repo | File read from working directory |

## Pointer Pattern

Keeps MEMORY.md under 2,200 chars by storing compact pointers:

```
# Instead of 200 chars:
"ACME Works uses Python 3.13.13, Meilisearch v1.14 on port 13213..."

# Write 40 chars:
  + /brain default acme-works (setup, search config)
```

## Memory Scoring Rubric (Layer 5 — Repo memory/)

Each entry in `memory/` is scored on 4 dimensions (0–3 each). Minimum total: **7/12**.

| Dimension | 0 | 1 | 2 | 3 |
|-----------|---|---|---|---|
| **Durability** | Gone next week | Month | Quarter | 6+ months |
| **Reuse** | Never again | Once more | Regularly | Every session |
| **Non-obviousness** | Everyone knows | Common knowledge | Tricky | Wouldn't guess |
| **Risk if forgotten** | No impact | Mild annoyance | Wastes time | Blocks work |

This prevents memory bloat — only durable, reusable, non-obvious, high-impact knowledge gets saved.

## Boot Survivability & Launch Agents

| Service | Launch Agent | Plist template |
|---------|-------------|----------------|
| Ollama | `com.ollama.serve` (bundled with Ollama app) | Built-in |
| Docker Desktop | `com.docker.docker` | `docs/templates/com.docker.docker.plist` |
| Legacy Sync | `com.legacy-brain.sync-watch` | Created by `scripts/install-legacy-sync.sh` |
| Hermes Gateway | `ai.hermes.gateway` | Created by Hermes Agent install |
| Cortex Dashboard | `com.hermes.cortex-dashboard` | `docs/templates/com.hermes.cortex-dashboard.plist` |

**Plist template convention:** Templates in `docs/templates/` use `CORTEX_HOME` as a placeholder. Replace before installing:
```bash
sed "s|CORTEX_HOME|${CORTEX_HOME}|g" template.plist > ~/Library/LaunchAgents/name.plist
```

## Profile Management Commands (Legacy)

| Command | Purpose | Status |
|---------|---------|--------|
| `hermes profile create <name>` | Create a profile | Only needed if running multiple simultaneous gateway instances |
| `hermes profile delete <name>` | Remove a profile | Rarely needed |
| `hermes profile list` | List all profiles | Useful for cleanup |
| `hermes profile alias <name>` | Create a shell wrapper | Not needed in uber-agent mode |

## Mass Setup Pattern (Current — mycortex Sources)

```bash
export PATH="$HOME/.bun/bin:$PATH"
for src in project-a project-b project-c; do
  dir="$HOME/brain/$src"
  [ -d "$dir" ] || mkdir -p "$dir"
  [ ! -d "$dir/.git" ] && git -C "$dir" init
  mycortex sources add "$src" --path "$dir" --name "$src"
  mycortex sync --source "$src" 2>/dev/null || true
done
```

## Pitfalls

- **Memory budget saturates fast without the pointer pattern.** MEMORY.md has a 2,200-char limit. Every entry above ~120 chars steals budget from other entries. Use compact pointers in MEMORY.md and store detail in `~/brain/default/references/` or `~/brain/<project>/references/`. Run `bash scripts/check-memory-budget.sh` regularly.
- **Brain source federation is single-directional.** Federated (`~/brain/default/`) is auto-searched. Isolated (`~/brain/<project>/`) is not — you must explicitly prefix with `--source <project>`.
- **`mycortex` may not be in PATH.** It's installed at `~/.bun/bin/mycortex`. Always verify with `export PATH="$HOME/.bun/bin:$PATH"`.
- **Brain directories need content.** mycortex sources show "0 pages, never synced" until you write .md files, commit them, and run `mycortex sync --source <name>`.
- **mycortex sync requires a clean git repo.** Dirty brain directories with uncommitted changes cause sync to fail silently.
