---
language: shell
tags: [git, advanced, bisect, reflog, hooks, worktree]
title: Git Advanced — bisect, reflog, hooks, worktrees
description: Advanced Git techniques — binary search for bugs, recovery tools, automation hooks, and parallel worktrees.
source: pattern
```

```bash
# ── Bisect (Binary Search for Bugs) ──
git bisect start                            # start bisect session
git bisect bad                              # current commit is broken
git bisect good v1.0                        # known good commit
# Git checks out the midpoint. Test it, then:
git bisect good                             # this commit is good
git bisect bad                              # this commit is bad
# Repeat until the first bad commit is found
git bisect reset                            # end bisect session
# Automated bisect:
git bisect start HEAD v1.0
git bisect run python test_script.py        # auto-run test at each step

# ── Reflog (Recovery) ──
git reflog                                  # every action you've taken
git reflog --relative-date                  # with readable timestamps
git reset --hard HEAD@{5}                   # go back to state from 5 steps ago
git checkout HEAD@{2}                       # inspect a previous state
git reflog expire --expire=30d --all        # keep 30 days of reflog

# ── Git Hooks (.git/hooks/) ──
# pre-commit: run lint/tests before commit
# prepare-commit-msg: auto-format commit messages
# commit-msg: validate commit message format
# pre-push: run full test suite before push
# post-receive: deploy after push (server-side)
# 
# Hook template (pre-commit):
#   #!/bin/sh
#   npm run lint || exit 1
#   npm run typecheck || exit 1
# 
# Manage hooks with: ghooks, husky, pre-commit (framework)

# ── Worktree (Multiple Branches at Once) ──
git worktree add ../my-feature feature/login    # checkout branch to separate dir
git worktree add -b new-feature ../new-feature main  # create + checkout new branch
git worktree list                                # all worktrees
git worktree prune                               # remove stale worktree records

# ── Stash ──
git stash push -m "wip: auth work in progress"   # save changes
git stash list
git stash pop                                    # apply + drop top stash
git stash apply stash@{2}                        # apply specific stash without dropping
git stash drop stash@{1}                         # drop specific stash
git stash clear                                  # remove all stashes
git stash branch new-feature stash@{0}          # create branch from stash

# ── Advanced Logging ──
git log --oneline --graph --all --decorate       # full history DAG
git log --diff-filter=M --name-only              # files modified in commits
git log -S "functionName" --source --all         # find where code was added/removed
git shortlog -sn                                 # contributor commit count
git blame file.py                                # who changed each line last
```
