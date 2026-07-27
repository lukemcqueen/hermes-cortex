# Scope Banner Patterns (from 2026-06-22 session)

Exact text used in the June 22 documentation scope update. Copy-paste these for new docs, modifying the audience description as needed.

## AGENTS.md — root-level agent guidelines

```
> **🪪 Scope:** This file serves two audiences:
> - **General agents** — the Architecture Principles, Agent Execution Contract, and Structured Development Pipeline below are universal to Hermes Cortex and recommended for every agent.
> - **Luke's deployment (Moses server)** — sections marked with a `⚡` tag are specific to Luke's multi-machine, multi-agent orchestration setup. They describe how Moses (the orchestrator agent) coordinates with peer agents Titus, Gisu, and Joseph. If you are not running Luke's setup, treat these as examples you can adapt.
>
> Everything unmarked is general Hermes Cortex guidance — apply it to any project using this repo.
```

## cron-job-recipes.md — recipe cookbook

```
> **🪪 Scope:** Most recipes in this cookbook are **general** — any Hermes user can adapt them. Recipes marked with `⚡` are from **Luke's deployment (Moses server)** and reference his specific setup (Moses as orchestrator, peer agents Titus/Gisu/Joseph, KST timezone, Telegram delivery). Treat those as concrete examples you can customize for your own setup.
```

## agent-contract — generalized operator notification

```
### 7.5 Operator Notification Protocol

When any Hermes Cortex agent receives a task from an upstream orchestrator
agent, it MUST notify its human operator before executing the task. This
ensures the operator is aware of what the agent is doing and can intervene
if needed.

> **Example (Luke's deployment):** The Moses orchestrator delegates to peer
> agents Titus, Gisu, and Joseph. Each peer notifies Luke via Telegram before
> acting on Moses's task.
```

## Section heading tags (consistent pattern)

Use `⚡` prefix in the heading, then a clear parenthetical:
- `## ⚡ Daily Priority Check-in (Luke's multi-agent setup)`
- `## ⚡ Agent Handoffs (Luke's deployment — session-to-session notes)`
- `## ⚡ 🌅 Daily Morning Briefing (Luke's setup — customizable example)`
- `## ⚡ Consolidated Nightly Window (Luke's deployment — 02:00–05:00 KST)`
- `### ⚡ 2026-06-19 — Monitoring timestamps switched to KST (Seoul time)`

## General utility skills (not deployment-specific)

Skills like `auto-remediation`, `eval-harness`, `weekly-auto-fix` that have `author: Moses` but are general-purpose tools: tag the section heading with `(general — applies to all agents)` instead of `⚡`.

```
### 2026-06-15 — Auto-remediation system (general — applies to all agents)
```