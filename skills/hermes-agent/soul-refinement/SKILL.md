---
name: soul-refinement
description: "Daily SOUL.md refinement process — mine sessions for lessons, apply corrections, codify principles. Optional per-agent Bible insight integration for daily Scripture reading."
version: 1.0.0
author: Hermes Cortex
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

## Template Curation — Consolidation & Size Budget (learned 2026-08-03)

The template (`docs/templates/SOUL.md`) and deployed `~/.hermes/SOUL.md` have a
**size budget enforced by the doctor** (`check_soul_sync` in cortex_doctor/checks.py):
**WARN >15K, FAIL >20K.** A template that grows past 20K makes every fresh
deploy FAIL its own identity document — the budget must win over content growth.

### Canonical structure: 12 principles

Principles accumulate from user corrections. When the count drifts toward
20-30+, **consolidate by theme** back to the canonical 12 (2026-08-03: 34 → 12):

1. Loop Governance — Mandatory Pre-Work Sequence (MCP-Enforced)
2. Inbox Message Decision Framework (+ audit trail)
3. Verify Before Declare — Real Work, Real Output
4. Be Proactive — Fix, Test, Document
5. Own Every Issue — Fix First, Prove Second
6. Always Do the Right Way — Canonical Paths
7. Be Concise — Every Word Earns Its Place
8. Protect the System — Security, Privacy, Stability
9. Design for the Full Deployment Matrix
10. Test Small Before Scaling
11. Agent Cron Management
12. Not Done Until Tested — End-to-End Verification

### Consolidation rules

- **Merge by theme, preserve every guardrail.** Each merged principle carries
  the actionable content of all its source principles (provenance dates inline).
- **Marker preservation is mandatory.** The doctor's `_extract_soul_markers`
  extracts bolded phrases (`- **What I did**`, `- **Proactive**`, etc.) and
  requires template ↔ deployed parity. After any merge, verify:
  ```bash
  python3 -c "
  import sys; sys.path.insert(0, 'ops/scripts/manage')
  from cortex_doctor.checks import _extract_soul_markers
  from pathlib import Path
  m = _extract_soul_markers(Path('docs/templates/SOUL.md'))
  print(len(m))"  # must equal the pre-merge count (14 as of 2026-08-03)
  ```
  The audit-trail markers ("What I did", "How I verified", "How the user learns
  about it", "Where it's logged") must stay **bold list items** — inlining them
  as prose silently drops them from the marker set.
- **Scripture stays at ONE anchor entry.** The daily-bible cron needs the LAST
  `### Book —` entry to know the next book. Keep exactly one (e.g. Colossians);
  archive older entries (full content lives in `~/brain/<agent>/bible/`).
- **Do NOT raise the doctor thresholds** to accommodate a bloated template —
  the content must fit the budget, not the budget stretch to the content.
- **Keep the template under 20K** (ideally ≤16K so a fresh deploy lands at WARN,
  not FAIL).

### Sync after curation

1. Patch `docs/templates/SOUL.md` (repo source)
2. Rebuild deployed `~/.hermes/SOUL.md` from template + agent-specific sections
   (Identity / Core Mission / Core Traits / Final Directive) — use a script, not
   manual copy, to avoid dropping the Hermes-docs paragraph
3. Run the doctor `check_soul_sync` — markers 14/14, sync PASS, size ≤ WARN
4. Commit template + skill together; broadcast via `agents-doc-broadcast.py`

### How soul-merge propagates refinements (learned 2026-08-03)

`soul-merge.py` only propagates template sub-points that carry a **bold marker**
(`**Text**`) into deployed copies — plain prose additions to a principle's
body are invisible to it. So:

- Write each new guardrail as its own bold-marker line, e.g.
  `**Governance fixes fail closed** — never delete or weaken enforcement to
  silence a warning; warn+exit0 is a bypass. <!-- Added YYYY-MM-DD -->`.
  A bare sentence appended to a paragraph will never reach the fleet.
- Multi-line (wrapped) sub-points ARE propagated whole as a block since the
  `_find_missing_subpoints` fix (2026-08-03); earlier, only the marker line
  propagated and continuation lines were silently dropped, truncating the
  guardrail in every deployed copy.
- After patching the template, run `soul-merge.py` and verify the new marker
  line AND its continuation lines landed in `~/.hermes/SOUL.md` before
  committing — a truncated deployed copy passes the doctor's marker check
  (markers match) while silently missing half the guardrail.

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
