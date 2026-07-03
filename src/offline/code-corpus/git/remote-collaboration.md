---
language: shell
tags: [git, remote, push, pull, github, collaboration]
title: Git Remotes — push, pull, fetch, and collaboration
description: Working with remote repositories — GitHub/GitLab, authentication, and collaboration patterns.
source: pattern
---

```bash
# ── Remote Management ──
git remote -v                               # list remotes
git remote add origin https://github.com/user/repo.git
git remote set-url origin git@github.com:user/repo.git  # switch to SSH
git remote rename origin upstream
git remote remove origin

# ── Pushing ──
git push origin main                        # push branch to remote
git push -u origin feature/login            # push + set upstream (first time)
git push --force origin feature/login       # force push (careful!)
git push --force-with-lease feature/login   # safer force push
git push origin --delete feature/login      # delete remote branch
git push --tags                             # push tags
git push origin :refs/tags/v1.0             # delete remote tag

# ── Pulling & Fetching ──
git pull                                    # fetch + merge (default)
git pull --rebase                           # fetch + rebase (cleaner history)
git pull origin main                        # pull specific branch
git fetch                                   # get remote changes without merging
git fetch --prune                           # fetch + remove deleted remote refs
git fetch origin feature/login              # fetch specific branch

# ── Authentication ──
# SSH key (recommended):
#   ssh-keygen -t ed25519 -C "you@example.com"
#   cat ~/.ssh/id_ed25519.pub  → add to GitHub/GitLab SSH Keys
#
# Personal access token (HTTPS):
#   Create at GitHub: Settings → Developer settings → Personal access tokens
#   git clone https://github.com/user/repo.git
#   Username: your-username
#   Password: your-token

# ── Syncing a Fork ──
git remote add upstream https://github.com/original/repo.git
git fetch upstream
git checkout main
git merge upstream/main
git push origin main

# ── Submodules ──
git submodule add https://github.com/lib/lib.git lib/
git submodule update --init --recursive
git clone --recurse-submodules https://github.com/user/repo.git
```
