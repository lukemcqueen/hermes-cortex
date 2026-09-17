---
name: cortex-preflight
description: >-
  DEPRECATED alias — merged into survey-before-action (2026-08-20). Load
  survey-before-action instead; its "Repo-Specific Pre-Flight" section covers
  git search, Hermes boundary, and deployment verification.
version: 1.1.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
related_skills:
  - survey-before-action
  - change-checklist
  - agent-fundamentals
---

# DEPRECATED — use `survey-before-action`

This skill was merged into `survey-before-action` on 2026-08-20 (which carries `aliases: [cortex-preflight]`). The repo-specific checks now live in its "Repo-Specific Pre-Flight" section.

## What to do instead

`skill_view('survey-before-action')` → "Repo-Specific Pre-Flight": git-missing-file check, governance-file workflow (orchestrators only), Hermes boundary table, deployed-vs-repo verification, agent-type check, stale-deploy-reference sweep, foreign working-tree check. Deployment pitfalls (SOURCE header checksums, lock purge, hook symlinks, PENDING-cycle scoring) are in its "Deployment Pitfalls" section.
