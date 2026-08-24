---
name: reliable-agent-design
description: "Use when designing or improving LLM agent workflows."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Reliable Agent Design — Production-Grade LLM Agent Principles

> Distilled from Dexter Horthy (HumanLayer, 12-Factor Agents, coined "context engineering") via the David Ondrej podcast (2026-08) and the public 12-factor-agents repo. These are the patterns that separate "demo agent" from "production agent" — use them when building or improving agent workflows in hermes-cortex.

## When to Use

- Designing a new agent workflow, cron, or multi-agent pipeline
- Reviewing hermes-cortex capabilities against industry best practice (gap analyses, HC-parties)
- Implementing agent improvements: context engineering, program design, quality gates
- Answering "how do we make our agents more reliable / top-1%?" questions

## The 12 Factors (condensed)

| # | Factor | Essence | hermes-cortex status |
|---|--------|---------|---------------------|
| 1 | Natural language → tool calls | NLI is the primitive | ✅ tools everywhere |
| 2 | Own your prompts | Versioned, explicit, no hidden strings | ✅ SOUL/AGENTS/skills |
| 3 | **Own your context window** | Token density, no junk, right format | ⚠️ lean modes exist; no dumb-zone discipline |
| 4 | Tools are structured outputs | Schema-first tool definitions | ✅ MCP tools |
| 5 | Unify execution + business state | One source of truth | ✅ task-db v2 + loop-gov DB |
| 6 | Launch/pause/resume | Durable, resumable workflows | ✅ cron + governance locks |
| 7 | **Contact humans with tool calls** | request_human_input as a tool (urgency/format/choices) | ✅ clarify tool, pushback gate |
| 8 | Own your control flow | Deterministic DAG, not prompt hopes | ✅ enforcer + hooks |
| 9 | **Compact errors into context** | Self-heal ≤3 retries, then escalate | ✅ auto-remediation |
| 10 | Small, focused agents | One agent per concern | ✅ 60+ focused crons |
| 11 | Trigger from anywhere | cron/webhook/chat entry points | ✅ full |
| 12 | Stateless reducer | Fold over event history | ⚠️ partially |
| +13 | **Pre-fetch context** | Deterministically fetch likely-needed context; free CPU ≠ inference | ❌ missing — session-start pre-fetch hook |

## The Four-Stage Program Design Ladder (Dexter's core method)

Before letting an agent "cook", walk these four stages in order — decisions are cheap up front, expensive after thousands of lines:

1. **Product** — user problem, measurable success metric, HTML mockups, write the blog post/PRD BEFORE building
2. **System architecture** — services, endpoints, tables, query outlines
3. **Program design** — call stack, file placement, types + method signatures (NOT implementation); code blocks a human can quickly read and approve
4. **Vertical slices** — end-to-end thin slice first (mock API → stub frontend → wire down → migration → logic → errors), testable at every step. Models default to horizontal builds with nothing testable along the way — you must force the order.

**Key insight:** *"If you can tell it a measurable output, the agent will move mountains."* Deterministic back-pressure (a number: conversion, latency, resource use) beats LLM-as-judge vibes.

## Context Engineering (Factor 3 deep dive)

- Everything is tokens in → tokens out; the context window is the ONLY primitive.
- Own it: high signal, minimal tokens, no wrong info, XML-style tagged formats over JSON (more token-efficient).
- **The dumb zone:** at ~50% context window the model degrades — it starts cutting corners, "context anxiety" sets in, it rushes and gives up. Compact into a doc and start a fresh session at ~50%.
- **Pre-fetch (F13):** if the model will likely need X, fetch X deterministically at session start (free CPU) instead of telling the model to fetch it (inference spend).
- Midwit curve: beginners give no context; midwits write 30-minute perfect prompts; experts say "it's in that file, read it and fix it" — high signal, low tokens.

## Quality Gates That Matter

- **Mutation-style test validation:** remove the model's patch, run its tests against pre-patch code — if they don't fail, the tests test nothing. (Verified missing from adversarial-verify.py as of 2026-08-24 — candidate improvement.)
- **Slop penalty:** benchmarks don't penalize bad design (maintainability has no fast oracle). Add heuristic slop checks: unnecessary try/catch/rethrow, pointless type casts, churn on unrelated lines.
- **Two-model review:** have a second frontier model review the first's output when trust matters.
- **Benchmarks are not evidence:** one-off problems, model sees the whole problem, no penalty for slop. Real evidence = can the codebase keep accepting features for months?

## Recommended hermes-cortex Improvements (gap analysis, 2026-08-24)

Priority order (see `references/dexter-12-factor-agents-research.md` for the full research + mapping):

1. **G1+G2:** Add `docs/adr/` (explicit decisions: API contract /v2 policy, pricing) + `docs/external/` (env var NAMES, service topology, test accounts) — context engineering for every agent
2. **G3:** Program-design template in dev-plan (call stack + types + vertical-slice order)
3. **G4:** Mutation-style test-validity gate in adversarial-verify.py (new tests must FAIL on pre-patch code)
4. **G7:** Deterministic pre-fetch at session start (pending tasks, recent corrections, cron status)
5. **G9:** Incident → reviewable PR/diff, not just an alert (auto-remediation emits PR-style summary)

## Pitfalls

- **Don't build a "light software factory"** (never read code). It works until it doesn't — then you're wading through slop for weeks with models that can't fix it. Stay in the loop via cheap program-design artifacts.
- **Inefficiencies ≠ bottlenecks.** Optimize the actual bottleneck (review/trust/value), not token-maxing or agent-count. "Stop playing with your coding agents and get back to work."
- **Agent should educate the human** — quizzes, visualizations, slow down when the operator loses grip of the codebase. Losing the touch is the failure mode.

## References

- `references/dexter-12-factor-agents-research.md` — full video salient points, 12-factor detail, and the hermes-cortex gap analysis
