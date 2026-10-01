# Pi Skill Bridge — External Agent Skill Loading

**Status:** Reference implementation deployed on `LAM2` (macOS host)  
**Author:** Pi coding agent (ephemeral), 2026-10-02  
**Relevant skills:** `devops/docker-management`, `devops/postgres-docker`, `devops/mycortex`

---

## Problem

Hermes Agent skills are loaded via **MCP runtime injection** — the hermes-agent process maintains state, speaks PGMQ, and loads skill markdown into its LLM context on every turn. Pi (the coding agent harness) is **stateless across sessions**: each invocation is a fresh process with no MCP connection, no task DB, and no skill registry.

This means Pi cannot:
- Call `skill_view()` or any MCP tool
- Maintain a task DB entry across invocations
- Auto-load skills based on agent-flow classification

But Pi **can** read files and execute bash. That is enough to build a bridge.

---

## Solution: A File-Based Skill Index

Instead of MCP injection, Pi builds a **static index** of the skill library and queries it on demand.

### Architecture

```
~/hermes-cortex/skills/               # Source of truth ( canonical skill library )
  devops/docker-management/SKILL.md
  devops/postgres-docker/SKILL.md
  ...

~/.pi/skills-index.json               # Generated index (341 skills, rebuilt as needed)
  { name, category, description, version, path }

~/.pi/load-skills                    # CLI tool
  --search <query>    → find matching skills
  --name <name>       → load FULL skill content
  --cat <category>    → list skills in category
  --project           → auto-detect from PWD

~/.pi/skills-activate                # Shell function
  → runs load-skills --project
  → dumps briefing to ~/.pi/.pi-skill-context.md
```

### Why this works for stateless agents

| Hermes Agent | Pi (stateless) |
|---|---|
| `skill_view(name)` → loads into context window | `cat SKILL.md` → same content, manual load |
| `agent-flow classify task → load on_task skills` | `cd project && load-skills --project` → category detection |
| Task DB persistence across turns | File-based context dumped per session |
| MCP enforcer gates | No gates — Pi operates outside the governance boundary |

The **content is identical**. Skills are markdown. Pi reads the same markdown.

---

## Deployment (One-Time Setup)

### 1. Build the index

```bash
# Run once after skills change, or add to cron
python3 /tmp/build-skill-index.py   # Writes ~/.pi/skills-index.json
```

The script parses YAML frontmatter from every `SKILL.md` under `~/hermes-cortex/skills/`.

Sample output: `341 skills indexed`

### 2. Install the loader

```bash
# ~/.pi/load-skills  (chmod +x)
# ~/.pi/skills-activate  (source-able)
```

Both are plain bash. Only dependency: `python3` (for JSON parsing).

### 3. Activate in shell

Add to `~/.zshrc` or `~/.bashrc`:

```bash
# Auto-load Hermes Cortex skills in pi sessions
[ -f ~/.pi/skills-activate ] && source ~/.pi/skills-activate
```

When you start a pi session in a project directory, the briefing prints automatically.

---

## Usage Examples

### Search for a skill

```bash
~/.pi/load-skills --search "postgres"
devops/alembic-postgres-migrations
devops/postgres-docker
devops/postgres-schema-design
```

### Load full skill content

```bash
~/.pi/load-skills --name "postgres-docker"
# Dumps the entire SKILL.md with headers
```

### Auto-detect project category

```bash
cd ~/Developer/KOSCAP/koscap-mwi
~/.pi/load-skills --project
→ Detected category: devops
→ Lists 130 devops skills with descriptions
```

Detection rules (extensible in `load-skills`):
- `*/koscap*`, `*/hermes-cortex*` → `devops`
- `*/IONE*` → `devops`
- `*/rgm*` → `marketing-psychology`
- `docker-compose.yml` present → `devops`

---

## Limitations

| Limitation | Mitigation |
|---|---|
| No MCP gate enforcement | Pi operates outside governance; human must enforce rules |
| No task DB persistence | Pi sessions are ephemeral by design; results go to terminal/file |
| No automatic `begin_change()` / `end_change()` | Pi does not participate in Hermes change protocol |
| Skill updates require manual re-index | Run `python3 /tmp/build-skill-index.py` after skill changes |
| Full skill dump is large (~28k lines for devops) | Use `--brief` / `--project` (compact) instead of `--cat` |

---

## Integration with Pi Context

When `skills-activate` runs, it produces a **compact briefing** (~200 lines, not 28k):

```
# Project Skill Briefing
Detected category: devops

## Skills available for this project:
- **docker-management**: Manage Docker containers, images, volumes, and Compose.
- **postgres-docker**: Tune and configure PostgreSQL running inside Docker...
...
(130 skills in category devops)

## To load a specific skill, run:
    load-skills --name <skill-name>
```

This briefing is injected into the pi session context as a file (`~/.pi/.pi-skill-context.md`). Pi's model can reference it without the full bloat of 130 complete skill documents.

---

## Future Work

1. **Auto-re-index on git hook** — Add a `post-merge` hook to `~/hermes-cortex` that rebuilds `~/.pi/skills-index.json` after every `cortex-update.sh` run.
2. **Per-project skill pinning** — Allow a `.pi-skills` file in a project root that pins specific skills to always load.
3. **Embedding-based search** — Instead of text search, embed skill descriptions and queries into mycortex for semantic retrieval.
4. **Hermes ↔ Pi bridge daemon** — A small Python daemon that exposes Hermes MCP tools over sockets so Pi can call them via curl.

---

## Files

| File | Description |
|---|---|
| `~/.pi/skills-index.json` | 341-skill index with metadata |
| `~/.pi/load-skills` | bash CLI for querying/loading skills |
| `~/.pi/skills-activate` | Shell function for auto-detection |
| `/tmp/build-skill-index.py` | Python script to rebuild the index |
