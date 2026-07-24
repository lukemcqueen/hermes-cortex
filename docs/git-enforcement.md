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

Two git hooks that enforce the governance workflow in a multi-agent repo:

- **pre-commit** — automatically logs a scoring cycle on every commit (secondary logger). Now scores ALL staged files, not just the first.
- **pre-push** — four checks before allowing a push:
  1. **Governance lock** — requires an active `begin_change()` session
  2. **Syntax check** — parses every changed `.py` and `.sh` file (py_compile/bash -n)
  3. **Doc coverage** — warns if code/config changes without `.md` changes
  4. **Pull-before-push** — ensures local `main` isn't behind `origin/main`

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

### `pre-push` (rules #13 + verification gate)

Source: `ops/scripts/pre-push-pull`

**Workflow order:**

1. Make changes under governance (begin_change → work)
2. **Update documentation** — docs, AGENTS.md, skills that other agents consume
3. Push — the hook enforces three checks:

   | # | Check | What it does |
   |---|-------|-------------|
   | 1 | Governance lock | No active `begin_change()` session for this repo |
   | 2 | Syntax check | Parses every changed `.py` (py_compile) and `.sh` (bash -n) file at push time. Cannot be skipped — the hook runs the checker itself. |
   | 3 | Doc coverage | Warns when code/config files change without a corresponding `.md` change. Soft warning — doesn't block, but reminds agents to update docs. |
   | 4 | Pull-before-push | Local `main` is behind `origin/main` |

   All checks run automatically at push time. No marker files, no `touch` commands.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0    | All checks passed + marker consumed | Push proceeds |
| 1    | Any check failed | Fix the issue shown in the error message |

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

The installer deploys the source scripts to `~/.hermes-cortex/scripts/` and `cortex-update.sh` creates symlinks from `.hermes-cortex/hooks/` to those scripts. This means git pull + cortex-update keeps hooks current without manual re-install.

---

## Bypass Mechanisms

Emergency bypass — use only when a hook is causing a false positive:

```bash
# Bypass all hooks (pre-commit + pre-push)
git commit --no-verify -m "..."
git push --no-verify
```

Using `--no-verify` is logged to `no-verify-audit` cron and auditable. It's a conscious choice, not an invisible escape hatch. Pre-commit `SKIP_SCORE=1`, `SKIP_ADVERSARIAL`, and pre-push `SKIP_PRE_PUSH=1` bypass flags have all been removed — no env-var bypasses.

These are documented in AGENTS.md rule #13 and mentioned in each hook's header comment.

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
| Hook not running at all | Hook not symlinked into `.hermes-cortex/hooks/` | Re-run `cortex-update.sh --force-all` |
| `❌ $file — syntax error` | `.py` file has a Python syntax error | Fix the error and re-push |
| `❌ $file — shell syntax error` | `.sh` file has a shell syntax error | Fix the error and re-push |

---

## Related

- AGENTS.md — rule #10 (scoring), rule #13 (pull before push)
- `mcp-servers/loop-gov-mcp.py` — primary enforcer MCP server
- `ops/scripts/pre-push-pull` — the push hook implementation
- `ops/scripts/pre-commit-score` — the commit hook implementation
- `ops/scripts/install/install-score-hook.sh` — the installer
- `docs/troubleshooting.md` — general system issues