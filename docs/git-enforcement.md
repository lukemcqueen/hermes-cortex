# Git Enforcement

## What This Is

Two git hooks that prevent common workflow mistakes in a multi-agent repo:

- **pre-commit** — scores every change via `score-cycle` before allowing a commit
- **pre-push** — ensures local `main` isn't behind `origin/main` before allowing a push

They're part of the Agent Execution Contract (rules #10 and #13) and apply to every agent and human working on `hermes-cortex`.

---

## The Two Hooks

### `pre-commit` (rule #10: Score Every Change)

Source: `src/scripts/pre-commit-score`

Runs `score-cycle` on staged changes. If the scoring infrastructure isn't installed, it warns and still allows the commit — never a hard blocker unless `score-cycle` itself errors.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0    | Scored (or skipped, or score-cycle absent) | Commit proceeds |
| 1    | `score-cycle` failed unrecoverably | Check loop-governance setup |

### `pre-push` (rule #13: Pull Before Push, Always)

Source: `src/scripts/pre-push-pull`

Fetches `origin/main` and checks if your local branch is behind. Only blocks on `main` — feature branches pass through.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0    | Local is up to date (or not `main`) | Push proceeds |
| 1    | Local is N commits behind remote | `git pull --rebase origin main`, then push |

---

## Installation

Both hooks are deployed by a shared installer:

```bash
# Auto-detect repos and install
bash src/scripts/install-score-hook.sh

# Install into a specific repo
bash src/scripts/install-score-hook.sh --path ~/hermes-cortex

# Check which repos have hooks
bash src/scripts/install-score-hook.sh --check

# Remove hooks
bash src/scripts/install-score-hook.sh --remove
```

The installer copies the source scripts into `.git/hooks/` as standalone files (not symlinks). Re-run it after cloning a fresh copy of the repo.

---

## Bypass Mechanisms

Emergency bypasses — use only when a hook is causing a false positive:

```bash
# Skip pre-commit scoring
SKIP_SCORE=1 git commit -m "..."

# Skip pre-push pull check
SKIP_PRE_PUSH=1 git push
```

These are documented in AGENTS.md rule #13 and mentioned in each hook's header comment. They're meant for lockstep merges or CI/CD flows where the pull was already handled upstream.

---

## For Agents

If you're an agent working on this repo:

- Both hooks run automatically on every local `git commit` and `git push`
- When `pre-push` blocks you, the error message tells you exactly what to run
- If you see `❌ score-cycle failed`, check that `~/.local/bin/` is in your PATH
- If you're using Hermes Agent's `terminal()` tool, the hooks fire the same as in a human terminal

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Push blocked even though I just pulled | Remote received new commits since your last fetch | `git pull --rebase origin main` |
| `score-cycle` not found warning | `loop-governance` tools not installed | `bash ~/hermes-cortex/src/loop-governance/setup.sh` |
| Hook not running at all | Hook not copied into `.git/hooks/` | Re-run `install-score-hook.sh` |
| Bypass env var not working | Exported in wrong shell or subprocess | Prefix directly: `SKIP_PRE_PUSH=1 git push` |

---

## Related

- AGENTS.md — rule #10 (scoring), rule #13 (pull before push)
- `src/scripts/pre-push-pull` — the push hook implementation
- `src/scripts/pre-commit-score` — the commit hook implementation
- `src/scripts/install-score-hook.sh` — the installer
- `docs/troubleshooting.md` — general system issues