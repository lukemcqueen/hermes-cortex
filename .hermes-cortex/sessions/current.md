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
| Last commit | `7a364da` — 2026-06-29 17:31:40 |
| Working tree | dirty (2 files) |
| Unpushed | none |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-29 | `7a364da` | resolve merge conflict: use standard qwen2.5-coder Q4_K_M models
| 2026-06-29 | `1c2c67c` | fix: keep qwen2.5-coder:1.5b-64k as gen model for CPU compat
| 2026-06-29 | `2355ade` | feat: auto-detect qwen2.5-coder model based on available VRAM
| 2026-06-29 | `3c1d968` | self-learning: offline_code check + learn-on-miss commands
| 2026-06-29 | `ba65dca` | refactor: simplify skill_miner.py to checksum parser, add skill-miner-wrapper

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 2508 lines, 26 steps, idempotent |
| Skills | 0 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 1049 files (409386 LOC) |
| Shell files | 68 files (14319 LOC) |
| Markdown files | 741 files |
| Total | 2408 tracked files |
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

*Last updated: 2026-06-29 18:03 KST*
