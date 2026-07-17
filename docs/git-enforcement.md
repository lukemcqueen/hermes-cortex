# Git Enforcement

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

## Secondary Enforcement — MCP Server Is Primary

These git hooks are **secondary enforcers**. The primary enforcement layer is the
`loop-gov-mcp.py` MCP server, which blocks write tools (`write_file`, `patch`,
`terminal`, `skill_manage`, `cronjob`) unless an active governance lock exists.
Git hooks only catch changes that flow through `git commit` — the MCP server
catches ALL changes at the Hermes tool level.

## What This Is

Two git hooks that assist common workflow practices in a multi-agent repo:

- **pre-commit** — automatically logs a scoring cycle on every commit (secondary logger)
- **pre-push** — ensures local `main` isn't behind `origin/main` before allowing a push

They're part of the Agent Execution Contract (rules #10 and #13) and apply to every agent and human working on `hermes-cortex`.

---

## The Two Hooks

### `pre-commit` (rule #10: Score Every Change)

Source: `ops/scripts/pre-commit-score`

Runs `score-cycle` on staged changes for **automatic DB logging**. Enforcement of the governance lock is handled by the MCP server — this hook just ensures a cycle is recorded for every commit.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0    | Scored (or skipped, or score-cycle absent) | Commit proceeds |
| 1    | `score-cycle` failed unrecoverably | Check loop-governance setup |

### `pre-push` (rule #13: Pull Before Push, Always)

Source: `ops/scripts/pre-push-pull`

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
bash ops/scripts/install/install-score-hook.sh

# Install into a specific repo
bash ops/scripts/install/install-score-hook.sh --path ~/hermes-cortex

# Check which repos have hooks
bash ops/scripts/install/install-score-hook.sh --check

# Remove hooks
bash ops/scripts/install/install-score-hook.sh --remove
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
| `score-cycle` not found warning | `loop-governance` tools not installed | `bash ~/hermes-cortex/core/governance/setup.sh` |
| Hook not running at all | Hook not copied into `.git/hooks/` | Re-run `install-score-hook.sh` |
| Bypass env var not working | Exported in wrong shell or subprocess | Prefix directly: `SKIP_PRE_PUSH=1 git push` |

---

## Related

- AGENTS.md — rule #10 (scoring), rule #13 (pull before push)
- `src/mcp-servers/loop-gov-mcp.py` — primary enforcer MCP server
- `ops/scripts/pre-push-pull` — the push hook implementation
- `ops/scripts/pre-commit-score` — the commit hook implementation
- `ops/scripts/install/install-score-hook.sh` — the installer
- `docs/troubleshooting.md` — general system issues