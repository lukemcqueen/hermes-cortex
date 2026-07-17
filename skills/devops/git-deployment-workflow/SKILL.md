--- Full content (truncated) ---
---
name: git-deployment-workflow
description: "Deploy code by pushing to bare remote repositories (Capistrano-style deployment targets). Covers force push patterns, divergence handling, and multi-remote sync."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Git, Deploy, Bare-Repo, GitOps]
    related_skills: [github-repo-management, github-pr-workflow]
---

# Git Deployment Workflow

Patterns for deploying code to bare git remote repositories — deployment
targets like staging, production, or training servers that receive pushes
but are not collaboratively developed on.

## Core Principle

**Bare deployment remotes are push targets, not collaboration points.**
Never pull, rebase, or merge from a bare deployment remote. It may have
hotfix commits pushed directly by other tools or users, but you should
never try to reconcile with them — just overwrite with your canonical
history.

## Commands

### List deployment remotes

```bash

... [truncated]
--- End skill ---