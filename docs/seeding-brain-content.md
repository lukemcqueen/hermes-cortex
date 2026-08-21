# Seeding Brain Content

> **Version 1.0.0** — Published 2026-06-11
> Part of the [Hermes Cortex](https://github.com/fleet-operator/hermes-cortex) documentation suite.

A guide to filling your empty brain directories with useful content so legacy brain has something to search.

---

## Why Seed Your Brain?

After `install.sh`, your `~/brain/` directory tree exists but is **empty** — no `.md` files means legacy brain indexes zero pages. Running `bootstrap-brain.sh` will show `0 pages indexed` for every source. This guide walks you through adding starter content so your agent can actually find things.

---

## Quick Start: The 5-Minute Seed

Create these three files to give your agent immediate context:

### 1. System Overview (`~/brain/default/references/system.md`)

```markdown
# System Reference

## Operating System
- macOS 14.x Sonoma (or your actual OS)
- Intel/Apple Silicon

## Installed Tools
- Hermes Agent — AI agent runtime
- Ollama — local LLM server (nomic-embed-text:v1.5 for embeddings)
- legacy brain — knowledge brain (Postgres + pgvector, Docker)
- Docker Desktop — for Langfuse, kiwix, etc.
- nginx — reverse proxy (ports 13001+)
- fail2ban — brute force protection
- pf — packet filter firewall

## Key Paths
| Path | Purpose |
|------|---------|
| `~/.hermes/` | Hermes config, skills, plugins, cron, scripts |
| `~/brain/` | Knowledge sources (this directory) |
|| `~/.legacy-brain/` | legacy brain database (Postgres via Docker, pgvector on `:15432`) |

## Services
| Service | Port | Managed By |
|---------|------|-----------|
| Ollama | 11434 | launchd/systemd (localhost only) |
| Langfuse | 3000 | Docker Desktop |
| Cortex Dashboard | 8901 | launchd/systemd |
| Legacy Sync | — | launchd/systemd (120s interval) |
```

### 2. User Profile (`~/brain/default/references/user.md`)

```markdown
# User Profile

## About
- Name: {{your-name}}
- Role: {{your-role}}
- Timezone: {{your-timezone}}
- Primary language: {{language}}

## Preferences
- Preferred response style: {{concise/detailed/enthusiastic}}
- Work hours: {{hours}}
- Communication platforms: {{Telegram, CLI, etc.}}

## Common Tasks
- {{task 1}}
- {{task 2}}
- {{task 3}}
```

### 3. Cron Schedule (`~/brain/default/references/crons.md`)

```markdown
# Cron Jobs

| Schedule | Job | Type | Purpose |
|----------|-----|------|---------|
| Every 2m | legacy sync daemon | system service | Auto-sync brain files (decommissioned; mycortex uses the 15-min cron) |
| */30 * * * * | system-heartbeat | no_agent script | Health check (silent when healthy) |
| 0 */6 * * * | memory-to-brain | no_agent script | Sync MEMORY.md → legacy brain |
| 0 4 * * * | memory-pruning | LLM | Compress MEMORY.md entries |
| 0 5 * * * | memory-budget-check | no_agent script | Warn if memory near limit |
```

After creating these, run:

```bash
bash ~/.hermes/scripts/bootstrap-brain.sh
```

You should see `3 page(s) indexed` for `default` (or however many files you created).

---

## Brain Directory Templates

### `default/` — Federated (always searched)

The default source holds everything universally relevant:

```
~/brain/default/
├── references/
│   ├── system.md           # OS, tools, paths, services
│   ├── user.md             # Your profile and preferences
│   ├── crons.md            # All cron jobs and schedules
│   ├── docker.md           # Docker config and recipes
│   └── commands.md         # Common command patterns
├── lessons/
│   ├── index.md            # Master list of lessons learned
│   ├── git.md              # Git-related lessons
│   ├── docker.md           # Docker-related lessons
│   └── troubleshooting.md  # Repeated fixes
├── decisions/
│   ├── architecture.md     # Architecture decisions
│   ├── tool-selection.md   # Why you chose tool X over Y
│   └── workflow.md         # Process decisions
├── concepts/
│   ├── hermes-cortex.md    # How your system works
│   └── legacy-brain.md           # How the legacy brain works
└── ideas/
    └── inbox.md            # Capture zone for raw ideas
```

### `shared/` — Federated (household/family)

```
~/brain/shared/
├── household/
│   ├── wifi.md             # Network config, SSID, passwords
│   ├── devices.md          # Network devices and IPs
│   └── calendar.md         # Family schedule, events
└── hermes-memory/
    ├── current.md          # Auto-synced from MEMORY.md
    └── archive/            # Historical snapshots
```

### `<project>/` — Isolated (--source only)

```
~/brain/my-project/
├── references/
│   ├── api.md              # API documentation
│   ├── architecture.md     # Project architecture
│   └── stack.md            # Tech stack and versions
├── decisions/
│   └── index.md            # Project decisions log
├── conversations/
│   └── session-notes.md    # Key session outcomes
└── lessons/
    └── index.md            # Project-specific lessons
```

---

## Content Templates by Purpose

### Reference File Template

```markdown
# {{Topic}} Reference

## Overview
{{Brief description of what this covers}}

## Key Facts
| Attribute | Value |
|-----------|-------|
| {{attr 1}} | {{value 1}} |
| {{attr 2}} | {{value 2}} |

## Details
{{Expanded information. Use sections as needed.}}

### Section 1
{{Content}}

### Section 2
{{Content}}

## Related
- Link to related topics in other brain files
```

### Lessons Learned Template

```markdown
# {{Topic}} — Lessons Learned

## {{Date or Version}}

### Problem
{{What went wrong or what was discovered}}

### Root Cause
{{Why it happened}}

### Fix / Solution
{{What fixed it}}

### Prevention
{{How to avoid in the future}}

### Related Files
- {{path/to/relevant/file.md}}
```

### Decision Record Template

```markdown
# Decision: {{Title}}

**Date:** {{YYYY-MM-DD}}

## Context
{{What prompted this decision? What constraints existed?}}

## Options Considered
| Option | Pros | Cons |
|--------|------|------|
| {{Option A}} | {{pros}} | {{cons}} |
| {{Option B}} | {{pros}} | {{cons}} |

## Decision
{{What was chosen and why}}

## Consequences
{{What this means going forward}}
```

---

## After Seeding: Verification

Once you've added content:

```bash
# 1. Bootstrap — sync everything and check page counts
bash ~/.hermes/scripts/bootstrap-brain.sh

# 2. Query — test that legacy brain can find your content
legacy brain query "system reference"
legacy brain query "user profile" --source default

# 3. Heartbeat — verify legacy brain sources show as healthy
bash ~/.hermes/scripts/heartbeat.py --report

# 4. Repeat — add more files as you go. mycortex syncs automatically
#    every 2 minutes via the sync daemon.
```

---

## See Also

- [Knowledge Isolation Architecture](./knowledge-isolation-architecture.md) — How brain sources work
- [Memory Architecture (Pointer Pattern)](./agent-memory-pointer-pattern.md) — Compressed pointers
- [Architecture Overview](./architecture.md) — System architecture
- [bootstrap-brain.sh](../ops/scripts/install/bootstrap-brain.sh) — Post-install brain verification
