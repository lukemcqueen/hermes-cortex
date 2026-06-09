# Hermes Cortex — Current Session

> **Auto-tracked repo-state snapshot.** Committed to git so every contributor
> sees the current project status. The **Repo State** section is auto-refreshed
> by the update script. The **Session Notes** section is written by agents
> during active work — update it with `save-session` or edit directly.

---

## Project Identity

| Property | Value |
|----------|-------|
| Name | Hermes Cortex |
| Version | 1.0.0 |
| License | MIT |
| Repo | `github.com/fleet-operator/hermes-cortex` |
| Branch | `main` |

---

## Session Notes

<!-- Agents: update this section during active work. Keep it concise. -->

**Current focus:** —
**Active branch:** `main`
**Phase:** —

### Completed Work
- *(none yet in this session)*

### Open Tasks
- *(none)*

### Important Files
- *(none recorded)*

### Recent Decisions
- *(none recorded)*

### Known Constraints
- *(none recorded)*

### Current Errors or Risks
- *(none)*

### Test Status
- No test suite configured yet

### Suggested Next Action
*Verify the project_current_session.md file is correct, then commit.*

---

## Repo State

| Metric | Value |
|--------|-------|
| Last commit | `3261074` — 2026-06-09 11:09:53 |
| Working tree | clean |
| Unpushed | none |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-09 | `3261074` | feat: auto-save session system — project_current_session.md + cron
| 2026-06-09 | `c8f8071` | feat: add public-contribution meta-skill, SOUL.md template, nginx deployment skill
| 2026-06-08 | `eae1545` | fix: install-nginx.sh hardcoded ports 11003/11002 → 13001/13002
| 2026-06-08 | `1492f8d` | fix: dashboard default port 13703→8901
| 2026-06-08 | `59b4025` | security: audit fixes — enforce :? secrets, nginx 127.0.0.1, PII cleanup

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 1517 lines, 26 steps, idempotent |
| Skills | 20 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 42 files (32623 LOC) |
| Shell files | 19 files (4815 LOC) |
| Markdown files | 489 files |
| Total | 185 tracked files |
| Dashboard | Flask app + nginx proxy — Langfuse traces + system health |
| Scripts | 16 utility scripts (heartbeat, memory-sync, LLM scoring, service recovery) |
| OpenCode | 15 commands + 3 agents + 30 optional skills |
| Offline | code corpus (386 snippets, 26 languages) + kiwix ZIM + offline reader |

---

## Status Checklist

- [ ] Tests passing (no test suite configured yet)
- [ ] Dashboard health confirmed
- [ ] Langfuse traces flowing
- [ ] nginx config valid
- [ ] Skills manifest synced
- [ ] Install.sh tested on clean target
- [ ] SECURITY.md up to date
- [ ] README matches reality
- [ ] Changelog updated
- [ ] Tag synced

---

*Last updated: 2026-06-09 11:10 KST*
