# Pre-Commit Scoring Hook

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

## Secondary Logger — the MCP Server Is Primary

The pre-commit hook is now a **secondary logger**, not the primary enforcement mechanism.

**Primary enforcement is at the MCP tool level.** The `loop-gov-mcp.py` server blocks `write_file`, `patch`, `terminal`, `skill_manage`, and `cronjob` unless an active governance lock exists. You cannot write a file or create a cron without calling `begin_change()` first. This catches ALL changes — git-tracked or not, config-only, deployments, sudoers edits — at the Hermes tool level, before anything reaches disk.

This hook adds **automatic scoring on every `git commit`** so cycles get logged to the DB for data collection and self-improvement. It's optional for enforcement (the MCP server already handled that) but valuable for keeping the scoring DB populated without manual effort.

## How It Works

Every time you run `git commit`:

1. The hook fires before the commit is created
2. It reads the commit message from `.git/COMMIT_EDITMSG`
3. **Slugifies** it into a task ID: `precommit-<repo>-<branch>/<message-slug>`
4. **Queries** the loop-governance DB for the highest `cycle_num` with that task ID
5. **Auto-increments**: previous cycle 3 → this commit becomes cycle 4
6. **Runs `score-cycle`** with the task ID, staged file, and pass rate
7. **Creates a cycle** in the loop-governance DB (at `~/.hermes-cortex/data/loop-governance.db`)
8. **Prints** the decision and task so you can follow up with feedback

Note: step 6's governance-lock check is redundant — the MCP server already verified the lock at write time. But the scoring call itself is useful for keeping the DB populated.

### Example

```
$ git commit -m "fix: nginx returns 0 for uninstalled"
📊 score-cycle: LOOP 🔄 (task=precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled, pass-pct=100)
[main abc1234] fix: nginx returns 0 for uninstalled
```

The cycle is now in the DB with `task_id = precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled`, `cycle_num = 1`.

---

## Installation

### One-liner (via cortex-update)

If you already have `cortex-update` installed, the hook is deployed automatically
on every update. To force immediate installation:

```bash
cortex-update
```

This:
1. Copies `pre-commit-score` to `~/.hermes-cortex/hooks/pre-commit`
2. Copies `pre-push-pull` to `~/.hermes-cortex/hooks/pre-push`
3. Sets `git config --global core.hooksPath ~/.hermes-cortex/hooks/`

Step 3 is the key — `core.hooksPath` overrides the per-repo `.git/hooks/`
directory for **every git repository on the machine**. One config change, all
repos covered.

### Manual install

```bash
# Deploy the hook script
mkdir -p ~/.hermes-cortex/hooks
cp ~/hermes-cortex/ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit
chmod +x ~/.hermes-cortex/hooks/pre-commit

# Set global hooks path
git config --global core.hooksPath ~/.hermes-cortex/hooks/
```

### Verify installation

```bash
git config --global core.hooksPath
# → /home/<user>/.hermes-cortex/hooks

ls ~/.hermes-cortex/hooks/
# → pre-commit (pre-push also present if deployed)
```

Then test on any repo:

```bash
cd /tmp && mkdir test-hook && cd test-hook && git init
echo "hello" > test.txt && git add test.txt && git commit -m "test: hook works"
# → 📊 score-cycle: LOOP 🔄 ...
rm -rf /tmp/test-hook
```

---

## What the Hook Does NOT Do

| Concern | How it's handled |
|---------|-----------------|
| **Block commits** | The hook only blocks if `score-cycle` itself has an unrecoverable error. Normal LOOP/STOP/MOVE_ON decisions never block. |
| **Enforce feedback** | The hook creates the cycle but doesn't provide `feedback_accept`/`override`. That's the agent's (or human's) job — follow up with `loop-feedback accept <id>` or `loop-feedback override <id> --note "..."`. |
| **Run tests** | If `pytest.ini` is present, the hook runs the test suite and calculates a pass rate. If no tests exist, it assumes `pass-pct 100`. |
| **Handle binary/lock files** | Binary files (`.png`, `.jpg`, `.ico`) and lock files (`package-lock.json`, `yarn.lock`, `.lock`) are automatically excluded. |

---

## Bypassing the Hook

There is **no bypass** — `SKIP_SCORE=1` has been removed, and `git commit --no-verify` is a **logged, audited bypass** (see `agent-no-verify-audit` cron), never a workflow. The pre-commit hook also runs the **mandatory adversarial verification gate** on every staged script (A2 default, A4 for security/guard/hook/enforcer files) — a hook-rejected change must be **fixed, not bypassed**.

When the scoring stack itself needs repair, fix it via the sanctioned path (`cortex-update.sh` — it deploys the scorer on Linux and macOS), then commit normally through the hook. If you are mid-rebase-conflict-resolution, resolve the conflict — rebase replays do not run pre-commit, so the commit will already pass; there is no reason to bypass.

**The bypass is not a workflow.** If `--no-verify` appears more than once per month in the audit log, something is wrong — fix the tooling, don't learn to live around it.

---

## Closing the Feedback Loop

The hook creates the cycle. You still need to provide feedback so the governance
system can learn whether each cycle was good or bad.

### Via MCP (Hermes agents)

```python
# Find the cycle
mcp_loop_governance_cycle_query(task_id="precommit-hermes-cortex-main/nginx-returns-0-for-uninstalled")

# Accept it (correct decision)
mcp_loop_governance_feedback_accept(cycle_id=122, note="nginx health fix — 0 for uninstalled")

# Or override (wrong decision)
mcp_loop_governance_feedback_override(cycle_id=122, correct_decision="STOP", note="This change was complete, should have been STOP")
```

### Via CLI (scripts, pre-commit hooks, shell)

```bash
loop-feedback accept 122 --note "nginx health fix — 0 for uninstalled"
loop-feedback override 122 --note "Complete change, should STOP" --correct-decision STOP
```

---

## Architecture

```
          ┌──────────────────────────────────┐
          │  Hermes Agent (every session)  │
          │ begin_change() → write tools →  │
          │ cycle_query → feedback_accept() │
          └─────────┬────────────────────────┘
               │
          ┌─────────▼────────────────────────┐
          │  loop-gov-mcp.py (MCP server)  │
          │  PRIMARY ENFORCER        │
          │  Blocks write tools without   │
          │  active governance lock      │
          │  Catches ALL changes       │
          └─────────┬────────────────────────┘
               │ git commit
          ┌─────────▼────────────────────────┐
          │  pre-commit hook (score-cycle)  │
          │  SECONDARY LOGGER        │
          │  Auto-scores on commit      │
          └─────────┬────────────────────────┘
               │
          ┌─────────▼────────────────────────┐
          │  loop-governance.db       │
          │  ~/.hermes-cortex/data/         │
          └──────────────────────────────────┘
```

A single `core.hooksPath` setting in `~/.gitconfig` makes every repo use the
same hooks directory. The MCP server is registered with `hermes mcp add` and
applies to all agent sessions automatically.

> ⚠️ **The hooks run in EVERY repo — project repos included.** `core.hooksPath`
> is global, so the pre-commit/pre-push hooks fire in client/project repos
> (client-mwi, etc.) that have **no `ops/` tree and no `.hermes-cortex/`**
> inside them. A hook that resolves a tool via `$REPO_ROOT/ops/...` (the repo
> being committed IN) breaks every commit there — regression `faa0e929`, fix
> `72d6cdc3` (2026-08-04). Hooks must resolve shared tools with a candidate
> loop: repo-local first, then the canonically-deployed copy at
> `$HOME/.hermes-cortex/scripts/` (registered by cortex-update.sh on both
> Linux and macOS). See `enforcement-change-safety` Rule 6.

---

## Troubleshooting

### Hook doesn't fire
```bash
# Check hooksPath is set
git config --global core.hooksPath
# Should output: /home/<user>/.hermes-cortex/hooks

# Check hook file exists
ls -la ~/.hermes-cortex/hooks/pre-commit

# Check it's executable
test -x ~/.hermes-cortex/hooks/pre-commit && echo "executable" || echo "not executable"
```

### Cycle not created (hook says LOOP but DB empty)
```bash
# Manually test score-cycle
score-cycle --task "test-diagnostic" --cycle 1 --code-file /dev/null --json
# score-cycle is deprecated — MCP-based governance in use instead.
```

### Per-repo hook overrides global
Some projects set `core.hooksPath` locally. Check:
```bash
git config --local core.hooksPath # should be empty
git config core.hooksPath      # should show global path
```

### score-cycle not found
The hook **blocks the commit** (exit 1 — fail closed). Scoring is part of the
enforcement chain: a commit without a cycle record is invisible to governance.
Fix by running `cortex-update.sh` to deploy the scorer (installs
`~/.hermes-cortex/tools/loop-governance/score_cycle.py` on Linux and macOS),
then re-commit. Do NOT use `--no-verify`.

---

## Related

- [Adoption Enforcement (loop-governance skill)](../skills/devops/loop-governance/SKILL.md#section-adoption-enforcement) — the four-layer enforcement model
- `ops/scripts/pre-commit-score` — the hook script
- `mcp-servers/loop-gov-mcp.py` — the primary enforcer MCP server
- `ops/scripts/cortex-update.sh` — deploys the hook via `install_precommit_hook()`
- `core/governance/setup.sh` — REMOVED July 2026. MCP-based governance replaces CLI tools.
