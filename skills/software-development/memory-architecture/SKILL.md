---
name: memory-architecture
description: "Design and maintain agent memory system: MEMORY.md structure, privacy boundaries, gitignore per brain source, seed templates, pointer pattern, and PII prevention. Use when asked: 'clean up memory', 'separate public from private', 'prevent PII leakage', 'organize memory', 'seed memory files', 'gitignore memory'."
---

# Memory Architecture

Governs how agent memory (MEMORY.md / USER.md) is structured, protected, and maintained across installs. Not about what *content* to store — that's per-session judgment — but about the *architecture* of the memory system itself.

## Core Principles

1. **MEMORY.md < 2,200 chars** — injected every turn. Compress aggressively.
2. **Pointer pattern** — compact pointers in MEMORY.md, full detail in brain directories (`/brain m <topic>`).
3. **Privacy by default** — each brain source has `.gitignore` excluding MEMORY.md, USER.md, .env.
4. **Seed, don't migrate** — fresh installs get template seeds, not cloned memory from another machine.
5. **Stratify by audience** — private facts → MEMORY.md. Public knowledge → `docs/`. Stale tasks → never save.

## MEMORY.md Structure

Three sections, always in this order:

### System Topology
Machine config, OS, services, repo structure, Docker config. Facts about *the system the agent runs on*.

### Orchestration
Agent identity, model providers, other agents (Titus, etc.), brain topology, behavioral rules.

### Agent Context
Active skills, cron jobs, pointer references to brain directories for detail.

### What NEVER goes in MEMORY.md:
- **Public knowledge** — if another agent on another machine would benefit, it goes in `docs/`
- **Stale task artifacts** — completed "skill updates", "fixed bug X", "merged PR Y" — these are session results, not durable facts
- **PII** — real names, email addresses, tokens, passwords, personal domains, private URLs

## Privacy Architecture

Each Hermes instance owns its own private memory. No cross-machine leakage.

### Brain source `.gitignore`
Every brain directory (`~/brain/{source}/`) has a `.gitignore` that excludes:
```
MEMORY.md
USER.md
.env
.env.*
*.pem
*.key
*.cert
.DS_Store
Thumbs.db
```

This prevents accidental commits of per-instance config, secrets, or agent identity.

### Seed templates in `docs/templates/`
The public repo ships bootstrapping templates:

| Template | Purpose |
|----------|---------|
| `MEMORY.seed.md` | Starter MEMORY.md with sections, placeholders, and design principles |
| `USER.seed.md` | Starter user profile with fields for preferences and context |
| `gitignore.brain` | Standard `.gitignore` for brain source dirs |

These are **copied** (not shared) during install — each machine gets its own copy to fill in.

### Install script integration (`install.sh`)
Two dedicated steps enforce the architecture:

| Step | What |
|------|------|
| **5** — Brain .gitignore | Copies `gitignore.brain` to each brain source after directory creation |
| **9** — Seed memory files | Copies `MEMORY.seed.md` → `~/.hermes/memories/MEMORY.md` and `USER.seed.md` → `~/.hermes/memories/USER.md` (only if files don't exist) |

## When to Update

- User says "clean up memory", "separate public/private", "prevent PII leakage"
- User corrects memory content that shouldn't be there (PII, public knowledge, stale tasks)
- New brain source is added — needs its own `.gitignore`
- Seed templates change — update `docs/templates/` and version-bump

## Pitfalls

- **Don't gitignore retroactively** — .gitignore only prevents untracked files from being tracked. If MEMORY.md is already tracked in a repo, you need `git rm --cached` first.
- **Don't merge memory across machines** — MEMORY.md is per-instance. Never copy from one Hermes to another. The pointer destinations are different.
- **Don't commit seed templates as instance memory** — templates live in `docs/templates/`, not in `~/.hermes/memories/`. The install script copies them.
