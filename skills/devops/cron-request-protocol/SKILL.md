---
name: cron-request-protocol
version: 1.3.0
category: devops
description: >-
  Protocol for non-orchestrator agents to request cron job creation, updates,
  or removal via the agent inbox. Only orchestrators have the cronjob MCP tool
  in all contexts; other agents route requests to the orchestrator inbox
  (inbox_orchestrator) using this protocol.
tags: [cron, inbox, protocol, multi-agent, orchestration]
related_skills: [cron-job-management, agent-inbox, change-checklist]
---

# Agent Cron Request Protocol v1.0.0

## Problem

Only orchestrators (Moses, Esther) have the `cronjob` MCP tool in all
contexts. Other agents (Gisu, Joseph, Kustos, Titus) cannot create, update,
or remove cron jobs directly. When in doubt, route through the orchestrator
inbox.

## Solution: Inbox-based CRON requests

Any agent needing a cron change sends a structured inbox message to the
**orchestrator inbox** (`inbox_orchestrator`) with subject prefix
`🔧 CRON: <action>`.

### Message format

```
Subject: 🔧 CRON: create|update|remove
Priority: normal|urgent
To: orchestrator

CRON_NAME: <name>                        # Required — lowercase, hyphens
CRON_SCHEDULE: <expression>              # Required — e.g. "0 9 * * *", "*/30 * * * *"
CRON_PROMPT: <self-contained prompt>     # Required for LLM crons, omit for script crons
CRON_SCRIPT: <path/to/script.py>         # Optional — for no_agent crons
CRON_SKILLS: <skill1, skill2>            # Optional — comma-separated skill names
CRON_MODEL: <model-name>                 # Optional — e.g. "deepseek-v4-flash"
CRON_PROVIDER: <provider-name>           # Optional — e.g. "deepseek" (current fleet standard)
CRON_DELIVER: <origin|local|telegram:ID> # Optional — defaults to "origin"
CRON_TOOLSETS: <toolset1, toolset2>      # Optional — e.g. "web, terminal"
CRON_REASON: <why this change is needed> # Required — context for Moses
```

### Examples

**Create a new LLM cron:**
```
Subject: 🔧 CRON: create
Priority: normal
To: orchestrator

CRON_NAME: agent-daily-market-report
CRON_SCHEDULE: 0 8 * * 1-5
CRON_PROMPT: Produce a market report for the day ahead...
CRON_MODEL: deepseek-v4-flash
CRON_PROVIDER: deepseek
CRON_DELIVER: origin
CRON_TOOLSETS: web
CRON_REASON: Luke requested a daily market briefing on weekdays
```

**Update an existing cron:**
```
Subject: 🔧 CRON: update
Priority: urgent
To: orchestrator

CRON_NAME: local-agent-daily-system-brief
CRON_SCHEDULE: 0 10 * * *
CRON_REASON: Luke changed preferred briefing time from 9am to 10am KST
```

**Remove an existing cron:**
```
Subject: 🔧 CRON: remove
Priority: normal
To: orchestrator

CRON_NAME: old-unused-cron-name
CRON_REASON: This cron was replaced by agent-daily-market-report
```

### Workflow

1. **Agent** sends inbox message to the orchestrator inbox (`inbox_orchestrator`) via `inbox_send` MCP tool or `contact-orchestrator.sh` (Agent Bus, not file writes)
2. **The orchestrator's agent-bus cron** picks it up (Moses, or Esther during failover)
3. **The orchestrator** validates the request, applies the change via `cronjob()` MCP tool
4. **The orchestrator** sends reply to the requesting agent via `inbox_send` confirming: ✅ applied or ❌ failed (with reason)
5. **The orchestrator** CC's Luke on all cron changes for visibility

### Field rules

| Field | Required for | Notes |
|-------|-------------|-------|
| CRON_NAME | All actions | Must already exist for update/remove |
| CRON_SCHEDULE | Create | Accepts: "*/30 * * * *", "0 9 * * *", "every 2h", "2026-07-15T09:00:00" |
| CRON_PROMPT | Create (LLM cron) | Self-contained — cron runs without user present |
| CRON_SCRIPT | Create (script cron) | Relative to ~/.hermes/scripts/ or absolute path |
| CRON_SKILLS | Create (LLM cron) | Comma-separated list, loaded in order |
| CRON_MODEL | Create (LLM cron) | Model name, pinned at creation |
| CRON_PROVIDER | Create (LLM cron) | Provider name, pinned at creation |
| CRON_DELIVER | Create | "origin", "local", "telegram:12345", or "all" |
| CRON_TOOLSETS | Create (LLM cron) | Comma-separated: "web, terminal, file" |
| CRON_REASON | All actions | Why the change is needed — for audit trail |

### Validation rules (the orchestrator enforces)

1. **CRON_NAME** must match `^[a-z0-9][a-z0-9_-]*$` — lowercase, hyphens/underscores only
2. **CRON_SCHEDULE** must be parseable by Hermes cron scheduler
3. **CRON_PROMPT** must be non-empty for LLM crons; **CRON_SCRIPT** must point to an existing file for script crons
4. **Update** only changes the fields provided — leaves unspecified fields untouched
5. **Remove** is irreversible — verify with the requesting agent if priority is below `urgent`
6. **Cross-agent requests** (Titus/Gisu/Joseph asking for a cron on their own machine) — Moses can only manage crons on his own server. For remote agent crons, Moses creates the cron request inbox message for those agents to apply on their own machines, and CC's Luke.

### ⚠️ Critical distinction: Hermes crons vs. system-level agent workers

This skill covers **Hermes crons** — crons on the orchestrator's server, managed by the orchestrator via `cronjob` MCP tool. These are for bus infrastructure, health checks, and inbox processing.

Agents on other machines need a **different mechanism** — a system-level worker process that polls the bus:

| Type | Where it runs | Managed by | How to create |
|------|--------------|------------|---------------|
| **Hermes cron** | Orchestrator's server (Moses, Esther) | The orchestrator (`cronjob` tool) | Send `🔧 CRON` request to the orchestrator inbox |
| **Agent worker** | Each agent's own machine | Each agent (`crontab -e` or `systemctl --user`) | Agent installs script themselves |

**The `🔧 CRON` protocol does not apply to agent workers.** I cannot install or modify anything on another machine. The most I can do is ship the worker script to the repo and document the installation steps.

### Superseding/correction handling

An agent may send multiple CRON requests in quick succession, where a later
message overrides an earlier one.

**The orchestrator's handling:**
- **Timestamps are authoritative.** Process messages in chronological order
  by filename (ISO prefix: `YYYYMMDDHHMMSS`). If a correction arrives *after*
  a removal request, the correction wins — do not remove the cron.
- **No action needed for superseded messages.** Acknowledge the correction
  and delete the superseded request. Do not recreate a cron you never removed.
- **Reply to the latest message.** Send your response to the correction
  message so the agent sees the final outcome.
- **Do not batch-process sequentially.** Read all unread messages in one pass,
  determine the final intent, then act once.

### One-shot run requests

An agent may request a one-shot execution of an existing cron script
without changing its schedule.

**The orchestrator's handling:**
- **No `run_now` cron tool exists.** The `cronjob` MCP tool does not
  support triggering immediate execution.
- **Workaround:** Run the cron's script directly via `terminal`:
  ```bash
  bash ~/.hermes-cortex/scripts/<script-name>.sh
  ```
  or for scripts at the canonical path:
  ```bash
  cd "$HOME" && bash ~/.hermes/scripts/<name>
  ```
- **Watchdog behavior:** no_agent scripts following the watchdog pattern
  produce empty stdout when nothing needed doing — this is correct, not a
  failure. Report "already up-to-date" rather than treating silence as an error.
- **If the script doesn't exist as a standalone file** (e.g., an LLM-driven
  cron that runs a prompt, not a script), explain that one-shot execution
  isn't available via the tool and suggest waiting for the next scheduled run.
- **CC Luke** on one-shot requests so he knows a manual trigger was run.

## Agent checklist for requesting a cron change

Before sending a cron request to the orchestrator, verify:

- [ ] CRON_NAME uses correct naming convention (lowercase, hyphens)
- [ ] CRON_SCHEDULE is correct for the timezone (KST = UTC+9)
- [ ] CRON_PROMPT is self-contained (no references to ephemeral context)
- [ ] For script crons: CRON_SCRIPT path is valid on the orchestrator's filesystem
- [ ] CRON_REASON explains why the change is needed
- [ ] Priority is appropriate (urgent only for same-day needs)

## Auditing

All cron changes made via this protocol are:
- Logged to loop governance (the orchestrator scores each change)
- CC'd to Luke via inbox or Telegram
- Traceable to the requesting agent's inbox message
