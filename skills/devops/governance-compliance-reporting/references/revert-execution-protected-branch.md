# Revert Execution on Protected Branch

Once you've identified which commits to revert (see SKILL.md Phases 1-5), executing the revert on a GitHub-protected branch requires specific steps because the pre-push hook blocks `--no-verify` commits.

## Problem

`git revert --no-edit` creates commits bypassing the pre-commit hook. The pre-push hook blocks any commit logged as `--no-verify`:

```
❌  Push blocked: commit X was made with --no-verify
    Message: Revert "fix(mcp): DOGFOOD gate..."
    --no-verify bypasses the adversarial verify gate and all governance checks.
    Re-do the commit through the pre-commit hook.
```

## Solution: Squash Revert Through the Hook

Do NOT revert one commit at a time. Instead:

### 1. Revert all commits at once

```bash
git revert --no-edit <commit-a> <commit-b> <commit-c>...
```

Git creates one revert commit per target commit, in reverse chronological order. All are logged as `--no-verify`.

### 2. Squash into a single proper commit

```bash
# Move HEAD back to the tip before reverts, keep all changes staged
git reset --soft <the-tip-before-reverts>

# Commit through the pre-commit hook (identity auto-sourced from agent.env)
git commit -m "revert: strip N unwanted commits (<range>)
  
  Reverts commits that violated governance/violated orchestrator-only paths.
  Preserves <key-commits-to-keep>.
  
  Commits reverted:
  - abc123 desc
  - def456 desc"
```

The pre-commit hook runs all checks (doc audit, secret leak scan, change-validate, self-test, adversarial verify, score-cycle). If it passes, the single commit is clean and can be pushed.

### 3. Push

```bash
git push origin main
```

## Determining What to Keep vs Revert

### Identify your last legitimate commit

```bash
# Find the commit YOU (the orchestrator) last made before the agent batch
git log --oneline --author="Moses" --format="%h %ai %an %s" | head -5
```

This is your rollback target — everything non-critical after it gets reverted.

### Check what enforcement changes exist in the revert batch

Before reverting, examine each enforcement-critical commit to see if it contains a FIX or DAMAGE:

```bash
# Check pre-commit-score for STAGED_FILES guard
git show <commit> -- ops/scripts/pre-commit-score | grep "STAGED_FILES"

# Check enforcer plugin for skills gate changes
git show <commit> -- plugins/governance-enforcer/__init__.py | grep -A5 "tools until skills"

# Check MCP server for DOGFOOD gate
git show <commit> -- mcp-servers/loop-gov-mcp.py | head -20
```

**Keep:** Fixes to dead-code bugs (empty STAGED_FILES), enforcement additions (skills gate), doc syncs.  
**Revert:** Gutting enforcement files, relaxing gates, removing protections.

### Check ancestry

```bash
# Check if a commit is ancestral to your base (baked in, won't be reverted)
git merge-base --is-ancestor <commit> <your-base-commit> && echo "ancestral" || echo "on top"
```

Ancestral commits stay even after reset. Only "on top" commits are removed by the revert.

## Required: Agent Identity Is Auto-Sourced — Do NOT Set AGENT_ID

Hook-based operations (commit, push) no longer need `AGENT_ID`. Identity comes from
`~/.hermes-cortex/agent.env` (`AGENT_NAME=<your-agent>`), provisioned by
`cortex-update.sh` (or the `AGENT_NAME` env var). The hook fails closed with setup
instructions if it is missing. Do NOT hardcode or export `AGENT_ID` — it is obsolete
and grants no privileges.

```bash
# Verify identity is provisioned (no action needed if this prints a name):
cat ~/.hermes-cortex/agent.env   # → AGENT_NAME=<your-agent>
```

If `agent.env` is missing, provision it once per host (the hostname→agent mapping is
infrastructure and stays out of the public repo):

```bash
echo 'AGENT_NAME=<your-agent>' > ~/.hermes-cortex/agent.env
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

## Full Pre-Commit Hook Pipeline

When committing through the hook, these checks run in order:

1. **AGENTS.md sync check** — deployed copy matches repo
2. **Docs audit** — DOCS-INDEX.md and SKILLS-MANIFEST.md updated
3. **Secret leak detector** — flags echo+pipe patterns, hardcoded tokens
4. **Syntax check** — Python/bash/nginx syntax validation
5. **Change-validate** — OS-aware paths, cross-platform guards
6. **Orchestrator self-test** — verifies identity is host-derived (env can't spoof)
7. **Adversarial verify** — scans for 30+ attack patterns
8. **Score-cycle** — logs the commit to loop-governance DB

Any failure blocks the commit. Fix the issue and retry.
