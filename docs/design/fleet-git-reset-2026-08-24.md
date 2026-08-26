# Fleet-Wide Git Reset After History Rewrite (2026-08-24)

**Every agent with a pre-existing local clone of hermes-cortex must align to
the clean rewritten history.** Local HEADs are pre-rewrite (PII-bearing);
origin/main is the clean history. The fork is real (all hashes changed).

## Who needs this

| Agent | Host | Needs reset? |
|---|---|---|
| Esther | Linux primary | ✅ DONE (reset + pruned, verified) |
| Moses | (primary-orch) | ✅ **DO THIS FIRST** — already seeing the fork |
| Titus | macOS dev | ✅ needs reset |
| Joseph | web/infra | ✅ needs reset |
| Kustos | (security) | ✅ needs reset |
| Gisu | (comms) | ✅ needs reset |
| titusclaude | Titus (new) | ✅ fresh clone — no reset needed (nothing local) |

## The tool: `fleet-git-reset.py` (fixed 2026-08-24)

Pre-built for exactly this. **Bug fixed**: EXPECTED_REMOTE was the stale
`lukemcqueen` URL → tool refused the real repo. Now accepts
`lukemcqueen/hermes-cortex.git` (deployed to ~/.hermes-cortex/scripts/).

```bash
python3 ~/.hermes-cortex/scripts/fleet-git-reset.py --check   # dry-run
python3 ~/.hermes-cortex/scripts/fleet-git-reset.py --reset   # align to clean main
```

Safety guards (fail closed): only ~/hermes-cortex, verifies remote,
refuses dirty worktree without --force, refuses unreachable origin/main,
only aligns main.

## Manual equivalent (if the tool can't run)

```bash
git fetch origin
git reset --hard origin/main          # align local main to clean history
git reflog expire --expire=now --all && git gc --prune=now   # purge old PII objects
git branch | grep -E "pii-scrub|pr/[0-9]" | xargs -r git branch -D  # stale branches
bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force      # sync deployed state
```

## ⛔ Never

- `git pull --rebase` — pulls old history onto new → 3000+ conflicts, stuck
  rebase (caused the morning's loop).
- `git merge origin/main` — same.
- `git push --force` — blocked anyway.

## Evidence each agent must report

```
BEFORE: <old HEAD sha>  AFTER: 12b9a6ae (or newer)
git status: clean
dogfood: PASSED
```
