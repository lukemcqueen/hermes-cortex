---
name: cross-repo-sync
version: 1.0.0
category: devops
description: >
  Update the same file (config, docs, boilerplate) across multiple project
  repos in a single coordinated pass. Covers the full pipeline: parallel
  survey, batch content generation, bulk write, verification, and
  multi-repo git commit/push with real-world failure handling.
pinned: false
---

# Cross-Repo Sync

**Keep a file synchronized across all project repos in one pass.**

Use when a standard file (AGENTS.md, .gitignore, README, config template)
needs updating everywhere. Not for one-off per-repo work — only when the
same file class exists across many repos with repo-specific content.

## Workflow

### Phase 1: Inventory (survey)

First, discover all repos and understand their current state.

```bash
# Find all repos with the target file
find /Users/luke -maxdepth 4 -name "TARGET_FILE" -not -path "*/node_modules/*" 2>/dev/null

# Optionally check git repos too
find /Users/luke -maxdepth 4 -name ".git" -type d 2>/dev/null | sed 's|/.git||'
```

For each repo found, record:
- Repo path + current branch
- Whether `TARGET_FILE` exists and its current content hash
- Any repo-specific customization (so the batch content can preserve it)

> **Portability:** use `$HOME` or `~` in commands instead of a hardcoded
> username; on fleet machines the user dir differs (`/home/luke` vs
> `/home/user`).

### Phase 2: Batch content generation

Generate the new content ONCE (per variant if repos differ), then apply the
same content everywhere. Do not hand-edit per repo — that defeats the point.

```bash
# Generate the canonical new version to a staging file
cat > /tmp/new-TARGET_FILE <<'EOF'
... canonical content ...
EOF

# If repos need small per-repo differences, use placeholders + sed:
sed "s/__REPO_NAME__/$repo_name/" /tmp/new-TARGET_FILE > "$repo/TARGET_FILE"
```

### Phase 3: Bulk write

```bash
for repo in $REPOS; do
  cp /tmp/new-TARGET_FILE "$repo/TARGET_FILE"
done
```

### Phase 4: Verify

```bash
# All repos should now have identical (or placeholder-substituted) content
for repo in $REPOS; do
  echo "$repo: $(shasum "$repo/TARGET_FILE" | awk '{print $1}')"
done
```

### Phase 5: Multi-repo git commit/push

```bash
for repo in $REPOS; do
  (
    cd "$repo" || continue
    git add TARGET_FILE
    git commit -m "chore: sync TARGET_FILE to canonical version"
    git pull --rebase origin main 2>/dev/null   # pull before push
    git push origin main
  ) || echo "FAILED: $repo — investigate before moving on"
done
```

## Real-World Failure Handling

| Failure | Cause | Fix |
|---------|-------|-----|
| Push rejected (non-fast-forward) | Remote moved; you must rebase/pull first | `git pull --rebase origin main && git push` |
| `cp` fails on one repo | Path typo or missing dir | Stop, fix, re-run only that repo |
| Commit succeeds, push fails | Auth / branch protection | Report; the local commit is safe, retry push |
| Repo has uncommitted changes | Sync would clobber local work | Skip + report; never `git checkout --` a coworker's WIP |

**Never let one repo's failure silently abort the loop** — record failures,
finish the pass, then report the failed repos explicitly.

## Pitfalls

- ❌ **Hand-editing each repo's copy** — drift returns immediately. Generate once, apply everywhere.
- ❌ **Hardcoded absolute user paths** — breaks on other machines. Use `$HOME`.
- ❌ **Silent failures** — a repo that didn't get the update looks synced. Always run Phase 4 verification.
- ❌ **Pushing without pull-rebase first** — guaranteed rejections on shared repos.

## Related
- `git-deployment-workflow` — pushing to bare deployment remotes
- `repo-organization` — canonical repo structure
