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
| Repo | `github.com/lukemcqueen/hermes-cortex` |
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
| Last commit | `5ddcca5` — 2026-06-09 13:38:58 |
| Working tree | dirty (2 files) |
| Unpushed | none |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-09 | `5ddcca5` | Move agent infra to .hermes-cortex/ (Titus proposal)
| 2026-06-09 | `5437781` | Drop verse references from public SOUL.md template
| 2026-06-09 | `5590cfc` | Add Guard Your Speech principle to SOUL.md template
| 2026-06-09 | `40a272c` | Fix 2 bugs + add gaps found by Titus in real-world testing
| 2026-06-09 | `8b226a4` | Titus improvements: 6 fixes for out-of-box UX

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 1723 lines, 26 steps, idempotent |
| Skills | 20 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 42 files (32734 LOC) |
| Shell files | 21 files (5401 LOC) |
| Markdown files | 491 files |
| Total | 193 tracked files |
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

*Last updated: 2026-06-09 13:47 KST*
