# Session State — 2026-06-09

## Last Actions
- Created `.github/workflows/auto-pr-titus-branch.yml` — auto-PR on `titus/*` pushes (PRs #6 -> #7 -> merged `be76ddb`)
- Updated `change-test-loop` SKILL.md — step 0 (branch creation), Test Decision Matrix
- Updated `agent-contract` SKILL.md — Rule 7 (titus/* branch protocol)
- Updated PAT to include `workflow` scope; added `GH_TOKEN` repo secret
- E2E verified: push to `titus/e2e-test-2` → run #6 success → draft PR #8 created

## What's Working
- `titus/*` push → auto-creates draft PR ✅ (verified)
- PAT in keychain + repo secret `GH_TOKEN` provides auth
- Branch protocol committed to memory + agent-contract skill

## Cleanup Needed (Moses)
- Delete remote `titus/e2e-test-2` branch and close PR #8
- Delete remote `titus/test-workflow`, `titus/workflow-test-2`, `titus/fix-workflow-heredoc` (already cleaned locally)
- PR #7 is merged; PR #8 is the last test artifact

## Near-term Next Slice
- Moses merges PRs from `titus/auto-pr-workflow` (skill changes on that branch)

## Repo State

| Metric | Value |
|--------|-------|
| Last commit | `78e756e` — 2026-06-19 12:00:32 |
| Working tree | clean |
| Unpushed | 4 commits |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-19 | `78e756e` | fix: eval scripts clarify intended usage (Hermes agent session required)
| 2026-06-19 | `c655ee1` | fix: CST key collision in hermes_tz.py + service-recovery.py hardcoded KST - hermes_tz.py: 'CST' was defined twice (8 vs -6), dict overwrite meant   China Standard Time was unreachable. Split into CNST/CST_CN/CST_US. - service-recovery.py: use hermes_tz.format_timestamp() instead of   hardcoded KST, respects HERMES_TIMEZONE env var like siblings
| 2026-06-19 | `dba865a` | fix: remove --enabled-toolsets flag (not supported by Hermes CLI)
| 2026-06-19 | `3b837b5` | fix: install-hermes-crons.sh skill-based cron creation
| 2026-06-19 | `08bc0ff` | fix: hermes-cortex script issues from upstream pull

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 2396 lines, 26 steps, idempotent |
| Skills | 0 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 73 files (41396 LOC) |
| Shell files | 50 files (11626 LOC) |
| Markdown files | 522 files |
| Total | 695 tracked files |
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

*Last updated: 2026-06-19 12:00 KST*
