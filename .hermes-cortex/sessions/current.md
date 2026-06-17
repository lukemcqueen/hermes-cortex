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
| Last commit | `dded8fa` — 2026-06-17 15:22:35 |
| Working tree | dirty (7 files) |
| Unpushed | none |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-17 | `dded8fa` | Per-agent read tracking: read_by frontmatter + ?for=agent filtering in inbox API. Agents auto-see their sent messages as read.
| 2026-06-17 | `b4e4b1b` | Add pipeline-reference.md: canonical docs for 4 growth pipelines, cadence, and closed-loop flows
| 2026-06-17 | `7641f86` | Enhance collect-agent-skills.sh: include full SKILL.md content in reports for evaluation
| 2026-06-17 | `4f9ee11` | Complete skill collection pipeline: request/process transport, inbox microsecond fix, docs
| 2026-06-17 | `fa51121` | Register skill-report scripts in cortex-update.sh + add config template

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 2348 lines, 26 steps, idempotent |
| Skills | 0 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 67 files (40136 LOC) |
| Shell files | 46 files (10092 LOC) |
| Markdown files | 511 files |
| Total | 665 tracked files |
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

*Last updated: 2026-06-17 16:00 KST*
