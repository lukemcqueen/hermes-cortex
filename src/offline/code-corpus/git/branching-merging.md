---
language: shell
tags: [git, branching, merge, rebase, workflow]
title: Git Branching, Merging & Rebasing
description: Branch management, merge strategies, rebasing, and conflict resolution.
source: pattern
---

```bash
# ── Branch Management ──
git branch                                  # list local branches
git branch -a                               # list all (incl. remote)
git branch feature/login                    # create branch
git checkout feature/login                  # switch to branch
git checkout -b feature/login               # create + switch
git switch feature/login                    # modern switch (Git 2.23+)
git switch -c feature/login                 # create + switch
git branch -d feature/login                 # delete merged branch
git branch -D feature/login                 # force delete (unmerged)

# ── Merging ──
git checkout main
git merge feature/login                     # merge into main
git merge --no-ff feature/login             # force merge commit (no fast-forward)
git merge --squash feature/login            # squash all into one commit
git merge --abort                           # abort merge on conflict

# ── Rebasing ──
git checkout feature/login
git rebase main                             # rebase onto main
git rebase -i HEAD~3                        # interactive: squash/reword/reorder
git rebase --continue                       # continue after conflict resolved
git rebase --skip                           # skip problematic commit
git rebase --abort                          # abort rebase entirely

# ── Conflict Resolution ──
# After conflict: edit files to resolve, then:
git add file.py                             # mark resolved
git merge --continue                        # finish merge
# or for rebase:
git rebase --continue

# ── Cherry-pick ──
git cherry-pick abc1234                     # apply specific commit to current branch
git cherry-pick abc1234..def5678            # range of commits
git cherry-pick --continue                  # after resolving conflicts

# ── Workflow Strategies ──
# Git Flow: feature → develop → main (classic)
# GitHub Flow: feature → main (PR + merge, simple)
# GitLab Flow: feature → main → production (environments)
# Trunk-based: short-lived branches → main (CI + feature flags)
```
