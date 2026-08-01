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
git remote -v | grep -E "deploy|staging|prod" || git remote -v
```

### Deploy: force-push the current branch

```bash
git push --force deploy main
```

`--force` is correct here because the bare remote is a snapshot target. The
deploy remote's post-receive hook typically checks out the tree or runs a
deploy script (Capistrano-style), so what matters is the pushed tree, not
history continuity.

### Deploy a specific local branch to a named remote branch

```bash
git push --force deploy feature/foo:main
```

### Deploy with divergence handling (safe default)

If you want to be defensive about clobbering a remote that *might* have
meaningful hotfixes, first fetch and compare:

```bash
git fetch deploy
git log --oneline deploy/main..origin/main | head
# If the deploy remote is strictly behind your canonical history, force push is safe
git push --force deploy main
```

If the deploy remote has commits *not* in your history, decide deliberately:
- Overwrite (deployment target, no one develops on it): `git push --force`
- Preserve (someone hotfixed it and you must keep that work): merge first, then push

## Multi-Remote Sync

When the same code must reach several bare remotes (e.g., staging + prod
training servers):

```bash
# Push to all deploy remotes in one pass
for remote in deploy-staging deploy-prod; do
  git push --force "$remote" main && echo "✓ $remote synced"
done
```

Or configure a push URL group once:

```bash
git remote set-url --add --push deploy git@staging:app.git
git remote set-url --add --push deploy git@prod:app.git
git push deploy main   # pushes to both
```

## Verification After Deploy

```bash
# Confirm the remote ref moved
git ls-remote deploy main

# Confirm the deployed tree matches your HEAD (compare tree SHAs)
REMOTE_SHA=$(git ls-remote deploy main | awk '{print $1}')
LOCAL_SHA=$(git rev-parse HEAD)
[ "$REMOTE_SHA" = "$LOCAL_SHA" ] && echo "✓ deployed tree matches HEAD" || echo "⚠ divergence: $REMOTE_SHA vs $LOCAL_SHA"
```

## Pitfalls

- ❌ **`git pull` from a bare deploy remote** — there is no working tree; pull fails or creates confusion. Use `fetch` + compare instead.
- ❌ **Merging deploy history into canonical history** — pollutes `main` with snapshot noise. Keep deploy remotes one-way.
- ❌ **Non-fast-forward push without `--force`** — rejected with "fetch first"; the fix is fetch + deliberate compare, not blind `--force`.
- ⚠️ **post-receive hooks** — some bare remotes run deploy scripts on receive. A rejected push means the hook failed; check the remote's logs before retrying.

## Related
- `github-repo-management` — cloning/forking, remotes, releases
- `github-pr-workflow` — PR-based collaboration for shared repos
- `cross-repo-sync` — same-file updates across multiple repos
