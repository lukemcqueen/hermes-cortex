# Memory Architecture: The Pointer Pattern

> **Version 1.0.0** — Published 2026-06-05
> Part of the [Hermes Cortex](https://github.com/fleet-operator/hermes-cortex) documentation suite.

**Keep your agent's short-term memory lean while preserving full detail on demand.**

## The Problem

Hermes agent memory is bounded at **2,200 characters** for `MEMORY.md` and **1,375 characters** for `USER.md`. These files are injected into every system prompt as a frozen snapshot. As your agent accumulates knowledge — system config, cron jobs, user preferences, operational lessons — it inevitably hits the ceiling.

When memory is full:
- New entries fail with "Memory at X% capacity"
- Important context gets evicted to make room
- The agent forgets things it once knew

## The Solution: Pointer Pattern

Instead of cramming everything into flat-file memory, keep only **compressed pointers** in `MEMORY.md` and move all **full detail** to a dedicated agent brain directory indexed by a semantic search engine (like gbrain).

```
MEMORY.md (2,200 chars)           Agent Brain (~/brain/<name>/)
┌──────────────────────┐          ┌──────────────────────┐
│ repos: two-repo      │   →      │ references/repos.md  │
│ crons: 16 jobs       │   →      │ references/crons.md  │
│ docker: 3GB VM       │   →      │ references/docker.md │
│ ──────────────────── │          │ lessons/index.md     │
│ ~120 chars each      │          │ decisions/           │
│ 7 entries ≈ 750 chars│          │ bible/               │
└──────────────────────┘          └──────────────────────┘
                                        ↕
                                   gbrain (embeddings)
                                   /brain m <topic>
```

Each pointer fits in ~120 characters and carries a `→ /brain m <topic>` hint so both the agent and the human know where the full detail lives.

## Step-by-Step Setup

### 1. Create the Agent Brain

Pick a location — typically `~/brain/<agent-name>/`:

```bash
mkdir -p ~/brain/moses/references
cd ~/brain/moses
git init
git remote add origin <your-private-repo>
```

Initialize gbrain and index this brain as its own source:

```bash
gbrain init
gbrain sync --source moses
```

### 2. Compress MEMORY.md

Review every entry in your `MEMORY.md`. For each one:

- **What does the agent absolutely need top-of-mind every turn?** That stays.
- **What can be looked up on demand?** That moves to the brain.

Each memory entry follows this format:

```
<topic>: <ultra-compact fact> → /brain m <reference-file-key>
```

Example transformation:

```diff
- Active crons: conversation-export (6h→gbrain), memory-to-brain-sync (6h, no_agent),
- memory-pruning (4am LLM), system-heartbeat (30min), gbrain-dream (3am),
- daily-morning-briefing (6:30am), briefing-analysis (Sun 7am),
- langfuse-llm-judge-scorer (M-F 12/8pm, weekends 10pm), hermes-update, brew-update.
+ Crons: 16 jobs (5min service-recovery → Sun 8am weekly-scan). → /brain m crons
```

### 3. Seed Brain References

Create a `references/` directory in your agent brain with one file per memory topic. Each file has the full detail the agent needs when it drills in.

```markdown
# references/crons.md

## Daily / Recurring

| Schedule | Name | Purpose | Type |
|---|---|---|---|
| Every 5min | service-recovery | Auto-restart nginx + Langfuse | no_agent script |
| Every 10min | system-alert | Memory/swap/disk thresholds | no_agent script |
| Every 6h | memory-to-brain | Sync MEMORY.md → gbrain | no_agent script |
| ... | ... | ... | ... |
```

Create a `references/INDEX.md` that maps pointer keys to files:

```markdown
| Pointer key | File | What it covers |
|---|---|---|
| `crons` | references/crons.md | All cron jobs, schedules, types |
| `docker` | references/docker.md | Docker config, resource allocation |
| `post-reboot` | references/post-reboot.md | Service verification checklist |
```

### 4. Index the Brain in gbrain

Sync your brain to gbrain so the agent can query it:

```bash
gbrain sync --source <name>
```

Verify it's searchable:

```bash
gbrain query --source <name> "cron service-recovery"
```

Now the agent can run the equivalent query automatically when it needs more detail.

### 5. Add the Auto-Resolve Directive to SOUL.md

Add a section to your agent's identity document that makes pointer resolution part of its core behavior:

```markdown
## Memory Architecture — Pointer Pattern

MEMORY.md holds only compressed pointers.
Agent brain (~/brain/<name>/) holds full detail, indexed by gbrain.

Rules:
1. Every MEMORY.md entry must fit in ~120 chars with a `→ /brain m <key>` pointer.
2. The agent brain must have a corresponding full-detail reference file.
3. When a memory entry is incomplete or more context is needed, automatically query the brain.
4. If no brain reference exists for a memory entry, create one immediately.
5. Regular pruning keeps both layers healthy.
```

### 6. Set Up Pruning

Two complementary approaches:

**Intelligent (LLM-driven):** A daily cron that reads MEMORY.md, reviews each entry critically, consolidates redundant entries, and removes stale ones. This requires the cron to use file I/O rather than the `memory` tool (which doesn't work in cron context).

```yaml
# Hermes cron definition (via cronjob tool)
- name: memory-pruning
  schedule: "0 4 * * *"
  prompt: |
    Read ~/.hermes/memories/MEMORY.md. Review each entry critically.
    Consolidate redundant entries. Remove stale ones. Use write_file to
    write the compressed version back.
```

**Mechanical (no_agent):** A simpler script that trims over-long entries, removes exact duplicates, and stays under the character limit.

```bash
# Runs Sundays at 5am as no_agent
python3 ~/.hermes/scripts/memory-compress.py
```

## Benefits

| Before | After |
|---|---|
| 98% memory utilization | 33% utilization |
| 7 verbose entries | 7 compact pointers |
| No escape hatch for overflow | Unlimited detail on demand |
| Important context evicted under pressure | All detail preserved in brain |
| Human must re-explain forgotten facts | Agent self-resolves from brain |
| Pruning is risky (might lose detail) | Pruning only affects pointers; full detail safe in brain |

## Example: Full Transformation

**Before** (98% — 2,174 chars):

```
Repos: public hermes-cortex (open-source skills/docs/scripts), private
private-data (system config + brain-* branches). Brain data ONLY
on brain-* branches. PII scrubbed.
Active crons: conversation-export (6h→gbrain)... [keeps going]
Skills created: cron-engineering, cortex-dashboard...
[HALLUCINATION GUARD] I have a recurring bug...
[Post-reboot] Proactively verify all services...
Moses brain autonomy: Luke explicitly gave me...
Docker Desktop is essential...
```

**After** (33% — 749 chars):

```
Repos: two-repo system (public/private). → /brain m repos
Crons: 16 jobs (5min → Sun 8am). → /brain m crons
Skills: cron-engineering, cortex-dashboard... → /brain m repos
[HALLUCINATION GUARD] Scan output before sending. → /brain m hallucination-guard
Post-reboot: verify 6 services + 6 launchd. → /brain m post-reboot
Moses brain autonomy: I curate ~/brain/moses/. → /brain m moses-brain-autonomy
Docker essential (observability). 3 GB VM stable.
```

## Requirements

- **Hermes Agent** (any version with the `memory` tool)
- **gbrain** (or any semantic search engine that indexes markdown files)
  - Install: `bun install -g github:garrytan/gbrain`
  - Free, open-source, self-hosted (Postgres + pgvector via Docker, or PGLite for dev)
- **Cron system** (Hermes cronjob tool or system crontab)
- **A private git repo** for the agent brain (optional but recommended for backup)

## Variations

**No gbrain?** The pointer pattern still works — the agent can use `terminal('cd ~/brain/<name> && grep ...')` for file-level search instead of semantic search. Less sophisticated but still functional.

**No separate brain repo?** Keep reference files anywhere the agent can read them. The key is separation of concerns — pointers in memory, detail in files.

**Multiple agents?** Each agent gets its own brain directory. gbrain supports multiple sources with `--source` filtering.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-06-05 | Initial release — pointer pattern, setup steps, pruning strategy |
