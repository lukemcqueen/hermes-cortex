# Hermes Cortex Git Hooks

Hooks are deployed by `cortex-update.sh` via the `install_precommit_hook()` function.

Deployed hooks are **absolute symlinks** created at:
- `~/.hermes-cortex/hooks/pre-commit` → `~/.hermes-cortex/scripts/pre-commit-score`
- `~/.hermes-cortex/hooks/pre-push` → `~/.hermes-cortex/scripts/pre-push-pull`
- `~/.hermes-cortex/hooks/post-commit` → `~/.hermes-cortex/scripts/post-commit-audit`
- `~/.hermes-cortex/hooks/post-push` → `~/.hermes-cortex/scripts/post-push-audit`
- `~/.hermes-cortex/hooks/post-merge` → standalone file (registered in cortex-update.sh)

**Do not place standalone hook files in this directory.** If a hook needs updating,
edit the source script in `ops/scripts/` and run `cortex-update.sh` to redeploy.

The doctor (`cortex-doctor`) verifies:
1. Deployed hooks exist
2. Deployed hooks are valid symlinks pointing to existing targets
3. Deployed hook content matches the repo source
