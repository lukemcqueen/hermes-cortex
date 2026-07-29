---
name: cron-pipeline-optimization
version: 1.0.0
category: devops
description: >-
  Attach skills to crons, constrain toolsets, add [SILENT].
author: Esther (Hermes Cortex)
license: MIT
platforms: [linux, macos]
---

# Cron Pipeline Optimization

## Purpose

Most Hermes cron jobs run without attached skills, without constrained
toolsets, and deliver verbose "nothing to report" messages. This skill
documents the four optimization patterns and provides a cron-to-skill
reference table so any agent can apply them.

## The Four Patterns

### 1. The Watchdog Pattern (`no_agent=True`)

**When:** The cron is a pure mechanical check — read a file, parse data, decide.

**Cost: $0 per run** — zero LLM tokens.

**How:** Convert from LLM-driven to `no_agent=True` with a Python/bash script.

**Script behavior:**
- Empty stdout → silent (nothing delivered to user)
- Non-empty stdout → delivered as the message
- Non-zero exit → error alert fires

**Example:** `agent-no-verify-audit` converted from LLM to no_agent watchdog.

### 2. The [SILENT] Contract

**When:** The cron needs an LLM but usually finds nothing to report.

**Cost: ~$0.03/run (input tokens only on silent days).**

**How:** End the prompt with:
```
If nothing notable to report, respond with exactly [SILENT]
```

The cron scheduler treats `[SILENT]` response as "do not deliver."

**Already applied to:** agent-fixer-*, agent-bus-*, agent-inbox-*, agent-weekly-loop-eval, agent-daily-soul-refinement, agent-memory-pruning, agent-agents-md-prune-apply, orch-skill-lifecycle

### 3. Skill Attachment

**When:** The cron follows a documented workflow pattern.

**Cost: Free** — skills load context that would otherwise be in the prompt.

**How:** Pass `skills: [<skill-name>]` via `cronjob action='update'` or in `install-crons.sh`.

Saves 30-70% of input tokens per run by putting workflow knowledge in the skill instead of the prompt.

### 4. Toolset Constraints

**When:** The cron doesn't need all default tools.

**Cost: 30-50% reduction in input tokens** by removing unused tool schemas.

**How:** `enabled_toolsets: [terminal, file]` — only tools the cron actually needs.

## Cron-to-Skill Reference Table

| Cron type | Best skill | Best toolsets | Pattern |
|-----------|-----------|---------------|---------|
| `agent-bus-*` | `agent-inbox` | `terminal` | LLM + [SILENT] + skill + toolsets |
| `agent-inbox-*` | `agent-inbox-automation` | `terminal` | LLM + [SILENT] + skill + toolsets |
| `agent-fixer-*` | `auto-remediation` | `terminal, file, web` | LLM + [SILENT] + skill + toolsets |
| `orch-skill-lifecycle` | `orch-skill-lifecycle` | `terminal, file, web` | LLM + [SILENT] + skill |
| `orch-skill-evaluate` | `skill-vetting` | `terminal, file` | LLM + skill + toolsets |
| `agent-weekly-loop-eval` | `loop-governance` | `terminal, file` | LLM + [SILENT] + skill |
| `agent-daily-soul-refinement` | `soul-refinement` | `terminal, file` | LLM + [SILENT] + skill |
| `agent-agents-md-prune-apply` | `documentation-scope` | `terminal, file` | LLM + [SILENT] + skill + toolsets |
| `agent-memory-pruning` | (self-contained) | `terminal, file` | LLM + [SILENT] + toolsets |
| `local-daily-sustainability` | `content-production`, `content-humanizer` | `web, terminal, file` | LLM + skills + toolsets |
| `agent-daily-bible-reading` | `agent-daily-bible-reading` | (none) | LLM + skill |
| All `no_agent=True` | (no_agent) | (no_agent) | Watchdog |

## How to Apply

### Step 1: List crons
```
cronjob action='list'
```

### Step 2: Update the cron
```
cronjob action='update' \
  job_id='<id>' \
  skills='["skill-name"]' \
  enabled_toolsets='["terminal","file"]'
```

### Step 3: Update source of truth
Patch `create_cron` block in install-crons.sh (agent-*) or install-orch-crons.sh (orch-*).

Args: `$1=name $2=schedule $3=script $4=prompt $5=skill $6=toolsets $7=deliver $8=workdir $9=no_agent ${10}=model ${11}=provider`

Note: `$6` (toolsets) is collected but not passed by the CLI `create` — set via cronjob API.

### Step 4: Verify
```
cronjob action='run' job_id='<id>'
cronjob action='list'
```
