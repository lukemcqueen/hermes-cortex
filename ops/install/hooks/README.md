# Steadfaste Fleet Git Hooks

Hooks are deployed by `cortex-update.sh` via the `install_precommit_hook()` function.

Deployed hooks are **absolute symlinks** created at:
- `~/.steadfaste-fleet/hooks/pre-commit` → `~/.steadfaste-fleet/scripts/pre-commit-score`
- `~/.steadfaste-fleet/hooks/pre-push` → `~/.steadfaste-fleet/scripts/pre-push-pull`
- `~/.steadfaste-fleet/hooks/post-commit` → `~/.steadfaste-fleet/scripts/post-commit-audit`
- `~/.steadfaste-fleet/hooks/post-push` → `~/.steadfaste-fleet/scripts/post-push-audit`
- `~/.steadfaste-fleet/hooks/prepare-commit-msg` → `~/.steadfaste-fleet/scripts/prepare-commit-msg-session`
  (stamps each governed commit with a `Cortex-Session:` trailer from the live lock, so a close
  review can scope itself to its own session; never blocks a commit)
- `~/.steadfaste-fleet/hooks/post-merge` → standalone file (registered in cortex-update.sh)

**Do not place standalone hook files in this directory.** If a hook needs updating,
edit the source script in `ops/scripts/` and run `cortex-update.sh` to redeploy.

The doctor (`cortex-doctor`) verifies:
1. Deployed hooks exist
2. Deployed hooks are valid symlinks pointing to existing targets
3. Deployed hook content matches the repo source
