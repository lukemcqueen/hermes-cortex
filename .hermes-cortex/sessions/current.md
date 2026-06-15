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
| Last commit | `e0a0531` — 2026-06-15 17:14:52 |
| Working tree | clean |
| Unpushed | none |
| Tag | `v1.0.0` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
| 2026-06-15 | `e0a0531` | Update session state [auto]
| 2026-06-15 | `db56ccd` | rename: moses-inbox-processor → process-agent-messages
| 2026-06-15 | `0c4df89` | fix: register moses-inbox-remediate.sh in deployment map fix: macOS sha256sum → shasum fallback in cortex-update.sh fix: Python 3.9 type hints in service-recovery.py fix: dynamic UID + PATH-based nginx paths in service-recovery.py fix: add missing Path import in system-alert.py
| 2026-06-15 | `618c46b` | feat: moses inbox remediation processor — auto-fix agent inbox messages within 10m
| 2026-06-15 | `82330a7` | fix: Linux compat for memory_pressure + correct threshold direction

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | `install.sh` — 2150 lines, 26 steps, idempotent |
| Skills | 0 skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | 54 files (37630 LOC) |
| Shell files | 39 files (8727 LOC) |
| Markdown files | 504 files |
| Total | 623 tracked files |
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

*Last updated: 2026-06-15 18:00 KST*
