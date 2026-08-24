---
name: context-engineering
description: "Context design for agents: pre-fetch, compaction, envelopes."
version: 1.0.0
author: Hermes Cortex (Esther, from verified 12-Factor Agents research, 2026-08-24)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [context-engineering, agents, pre-fetch, compaction, context-window, 12-factor, prompt-design]
    related_skills: [software-factory, session-manager, memory-architecture, autonomous-ai-agents]
---

# Context Engineering for Coding Agents

The context window is the ONLY primitive: tokens in → tokens out. Get the
best inputs to get the best outputs. This skill captures the verified
patterns from Dex Horthy's 12-Factor Agents (F3 own-your-context-window,
F13 pre-fetch) and how they were implemented in Hermes Cortex.

Full research bank: `references/12-factor-agents.md`.

## When to Use

- Designing what context an agent receives before/during a task (dispatch
  envelopes, cron prompts, subagent delegation).
- Adding pre-fetch of likely-needed context (repo rules, plans, history).
- Choosing what to compact vs keep when a session grows long.
- Building docs/adr + docs/external so context lives in the codebase.

## Core principles (F3 — own your context window)

1. **Information density over message shape.** XML/YAML tagged blocks in a
   single user message often beat standard chat turns — same info, fewer
   tokens, more attention.
2. **Compact at ~50% ("dumb zone").** Decide the hard things EARLY in the
   context window, write them to docs, restart fresh. Don't let a session
   run to 90% full before compacting.
3. **Own the format.** If the default message format wastes tokens, build
   your own. You want the flexibility to try EVERYTHING.
4. **Hide resolved errors.** Once a failure is handled, don't keep it in
   the window — it distracts and invites re-derivation loops.

## Core principle (F13 — pre-fetch deterministically)

> "If you already know what tools you'll want the model to call, call them
> DETERMINISTICALLY and let the model do the hard part of figuring out how
> to use their outputs."

Don't tell the agent "you may want to fetch X" — fetch X and include the
output. Free CPU ≠ inference tokens; pre-fetching costs CPU, letting the
model fetch costs tokens + round-trips + drift.

## Implemented pattern (Hermes Cortex, 2026-08-24)

`ops/scripts/executor_context_builder.py` — deterministic pre-fetch into
the execution_request envelope before dispatch. Sections in priority order,
budget-capped (~6000 chars, F3):

1. REPOSITORY RULES (AGENTS.md) + AGENT GOVERNANCE (CLAUDE.md)
2. PLAN (orchestrator-written slice plan)
3. TASK
4. RECENT GIT HISTORY
5. WORKTREE CHANGES (uncommitted diff stat)

Pitfalls learned building it:
- **Budget enforcement packs sections in priority order until full** —
  truncate the last block, never drop high-value rules.
- **Missing repo → return an error marker, never raise** (fail-open for
  the caller).
- **Missing/invalid plan is fine** — task alone still builds an envelope.
- **Never invent env names** — survey the registry (docs/external/env-vars.md)
  before introducing a variable.

## Context-in-the-codebase (point 7)

Files on disk are free context. `docs/adr/` for durable decisions
(context/decision/consequences, never rewrite — supersede), `docs/external/`
for env var NAMES (never values) + third-party services. A fresh session
should read these instead of re-deriving or asking.

## Pitfalls

- **parse_pass_pct-style regex traps**: when parsing tool output for
  context/scoring, search each token independently ('N passed', 'N failed',
  'N errors') — junk tokens between them ('69 warnings') break
  single-regex parsers and silently score wrong (errors scored as 100%
  pass, 2026-08-24).
- **Compaction is not free**: each micro-compact pass is a real model call
  and can break the provider prompt-cache prefix (bills as new input).
  Weigh cache-hit value vs compaction frequency (F3 + F13 tradeoff).
- **Pre-fetch is a bonus, never a blocker**: if the context builder fails,
  the dispatch must still proceed with empty context — wrap in try/except,
  never fail the request.

## References

- `references/12-factor-agents.md` — full verified research: 13 factors,
  video points (software-factory model, program design, benchmarks-vs-
  maintainability), the HC implementation map.
