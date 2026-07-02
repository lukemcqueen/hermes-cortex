# Agent Guidelines — Hermes Cortex


This file is read by many agent tools (Claude Code, Copilot, Codex, Hermes, etc.)
on session start. It orients any agent working on this repo.

> **🪪 Scope:** This file serves two audiences:
> - **Ge

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.548079+00:00


---

## ⚡ Daily Priority Check-in (Luke's multi-agent setup)


**Cron jobs:**
- `titus-daily-briefing` — 8:00am KST, posts to GitHub issue #1
- `daily-priority-checkin` — 8:30am KST, delivers to `origin` (Telegram)

**Purpose:** Start each day with focused align

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.548816+00:00


---

## ⚡ Luke's Deployment: Daily Priority Check-in


| Time | Agent | Action |
|------|-------|--------|
| 8:00am KST | Titus | Analyzes repos, posts briefing as comment on GitHub issue #11 |
| 8:30am KST | Moses | Reads latest comment via `gh api`. As

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.549741+00:00


---

## ⚡ Luke's Deployment: Cron Jobs Reference


| Cron | Schedule | Type | Purpose |
|------|----------|------|---------|
| `agent-auto-remediate` | `*/30 * * * *` | LLM+skill | Auto-fix cron/inbox/service issues |
| `remediation-sensor` | `*/5 * 

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.551076+00:00
