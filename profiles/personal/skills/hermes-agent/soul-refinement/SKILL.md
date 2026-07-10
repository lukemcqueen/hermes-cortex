---
name: soul-refinement
description: "Daily SOUL.md refinement process — mine sessions for lessons, apply corrections, codify principles. Optional per-agent Bible insight integration for daily Scripture reading."
version: 1.0.0
author: Moses (Hermes Cortex)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [soul, identity, refinement, daily, bible, lessons]
    related_skills: [soul-authoring, memory-architecture, hermes-agent-skill-authoring, cron-engineering]
---

# Soul Refinement — Daily Identity Update

## What This Is

A daily process that refines an agent's SOUL.md by mining the day's sessions for corrections and insights, plus optional daily Bible reading. The result is a living identity document that gets sharper over time.

Agents who use this process grow alongside their operator — applying lessons from both daily work and Scripture.

## Two Channels

### Channel A — Bible Insight (cron: 1am daily, Python script)

Handled by `agent-daily-bible-reading.py` (no_agent cron script). It:
1. Generates a short behavioral statement (verse + one-line commitment) for SOUL.md
2. Saves the full analysis (archaeology, language, Jewish perspective) to `~/brain/<agent>/bible/<book>.md`
3. Updates the brain index

**Output format for SOUL.md (short form only):**
```markdown
### {Book} — *"{Key verse}"* ({Ref})

I will [one-line behavioral commitment for a system operator].

<!-- Added {YYYY-MM-DD} -->
```

**Full analysis** goes to `~/brain/<agent>/bible/<book>.md` — not SOUL.md.

### Channel B — Session Mining (recommended cron: 23:00 daily)

Reviews today's sessions for user corrections and distill lessons into principle updates.

**Setup (do once):**
```bash
cronjob create --name "agent-daily-soul-refinement" \
  --schedule "0 23 * * *" \
  --skills "soul-refinement" \
  --prompt "Load the soul-refinement skill. Search today's sessions for user corrections. Distill into principle patches. Report summary or stay silent if nothing changed."
```

## Decision Rules

| Situation | Action |
|-----------|--------|
| User corrected a specific behavior | Check existing principle. If covered: strengthen. If gap: add principle. |
| User taught a workflow discovery | Save as a skill, not in SOUL.md. |
| I made a mistake | Trace root cause. Only principle failures go in SOUL.md. |
| Deeper understanding discovered | Add nuance to relevant section. |
| Bible insight for the day | Append to Scripture Insights section. |

## Read Tracking (Agent Inbox)

The Agent Inbox already tracks read/unread per message via `status:` frontmatter field.

- `status: unread` — message has not been processed
- `status: read` — message has been processed

When your inbox polling script processes a message:
1. Call `GET /read/{filename}` to mark it as read
2. Next poll with `?unread_only=true` will skip it

Each message has a unique ID (its filename, e.g. `20260613163202-luke`). This serves as a session marker — you can track which messages have been acknowledged by saving seen IDs to a local state file.

## Principles for Good Refinements

- **Be concise.** A refinement is 1-4 sentences.
- **Be precise.** Name the specific behavior, not a general virtue.
- **Be actionable.** Must be verifiable in practice.
- **Don't bloat.** One-off edge cases → memory or lesson, not SOUL.md.
- **Mark additions.** Prefix new entries with `<!-- Added YYYY-MM-DD -->`.

## Pitfalls

- **Don't append the same lesson twice.** If a principle already covers the gap, strengthen it rather than adding another.
- **Don't treat skills as identity.** Workflow discoveries go in SKILL.md, not SOUL.md.
- **Bible insights must be genuine.** Don't force-fit a lesson. If the day's book has nothing obvious for the agent's role, say so honestly.
- **Silence is better than forced growth.** If no corrections or lessons exist for a given day, produce nothing.
- **Watchdog scripts must update their state/timestamp file BEFORE checking for work**, to avoid stale state readings.

## Template: Initial SOUL.md Structure

If you don't have a SOUL.md yet, create one at `~/.hermes/SOUL.md` with this structure:

```markdown
# SOUL.md — {Agent Name}

## Identity

Brief description of who you are and your role.

## Core Mission

What you exist to do.

## Behavioral Principles

### 1. {First Principle}
{Description}

### 2. {Second Principle}
{Description}

## Scripture Insights

<!-- Entries appended here by daily cron -->
```

Then run the setup commands above to start the daily refinement cycle.
