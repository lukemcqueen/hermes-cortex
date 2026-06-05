---
language: shell
tags: [git, cli]
title: Git Workflow Commands
description: Common Git workflows: branching, merging, rebasing, squashing, cleanup.
source: pattern
---

```shell
#!/usr/bin/env bash
# ======= Workflow: Feature Branch =======
git checkout main
git pull origin main
git checkout -b feature/my-feature
# ... work, commit ...
git push -u origin feature/my-feature
# Open PR on GitHub

# ======= Workflow: Update branch from main =======
git fetch origin
git rebase origin/main          # cleaner history
# OR
git merge origin/main           # preserves merge commits

# ======= Workflow: Squash last N commits =======
git rebase -i HEAD~3            # pick first, squash rest

# ======= Workflow: Undo last commit (keep changes) =======
git reset --soft HEAD~1

# ======= Workflow: Undo last commit (discard changes) =======
git reset --hard HEAD~1

# ======= Workflow: Interactive add =======
git add -p                      # stage changes hunk by hunk

# ======= Workflow: Stash =======
git stash push -m 'WIP: feature X'
git stash list
git stash pop
git stash drop stash@{0}

# ======= Cleanup: Delete merged branches =======
git branch --merged main | grep -v '\*\|main' | xargs -r git branch -d

# ======= Show file from another branch =======
git show other-branch:path/to/file.py

```
