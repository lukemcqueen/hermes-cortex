---
language: shell
tags: [git, basics, workflow, version-control]
title: Git Basics — init, add, commit, log, status
description: Fundamental Git commands for everyday version control — staging, committing, viewing history, and undoing changes.
source: pattern
---

```bash
# ── Initialize & Configure ──
git init                                    # new repo in current dir
git init my-project                         # new repo in my-project/
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global init.defaultBranch main
git config --global core.editor code --wait

# ── Staging & Committing ──
git status                                  # current state
git add file.py                             # stage single file
git add .                                   # stage all changes
git add -p                                  # stage interactively (hunk by hunk)
git rm file.py                              # stage deletion
git mv old.py new.py                        # stage rename
git commit -m "feat: add user auth"         # commit staged
git commit -am "fix: typo"                  # stage + commit tracked files
git commit --amend                          # edit last commit message
git commit --amend --no-edit                # add to last commit without editing

# ── Viewing History ──
git log                                     # full history
git log --oneline                           # compact one-line
git log --graph --oneline --all            # branch graph
git log -p                                  # with diffs
git log --oneline --since="2 weeks ago"     # recent commits
git log --author="luke"                     # filter by author
git log --grep="fix:"                       # filter by message
git show HEAD                               # last commit details
git show abc1234                            # specific commit

# ── Undoing ──
git restore file.py                         # unstage + discard (working tree)
git restore --staged file.py                # unstage only (keep changes)
git reset --soft HEAD~1                     # undo commit, keep changes staged
git reset --mixed HEAD~1                    # undo commit, keep changes unstaged
git reset --hard HEAD~1                     # undo commit, discard changes
git clean -fd                               # remove untracked files/dirs
```
