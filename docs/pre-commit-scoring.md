# Pre-Commit Scoring Hook

## Mandatory — Every Commit, Every Repo, Every Dev Machine

This hook is **not optional**. Every developer working in this ecosystem must have
it installed on every machine they use. It is the enforcement mechanism for
[Rule #10](../AGENTS.md#10-score-every-change) of the Agent Execution Contract:
**score every change**.

Without the hook, manual scoring is forgettable. With it, every `git commit`
auto-creates a governance cycle. You can't forget — it's enforced before the
commit lands.

---

## How It Works

Every time you run `git commit`:

1. The hook fires before the commit is created
2. It reads the commit message from `.git/COMMIT_EDITMSG`
3. **Slugifies** it into a task ID: `precommit-<repo>-<branch>/<message-slug>`
4. **Queries** the loop-governance DB for the highest `cycle_num` with that task ID
5. **Auto-increments**: previous cycle 3 → this commit becomes cycle 4
6. **Runs `score-cycle`** with the task ID, staged file, and pass rate
7. **Creates a cycle** in the loop-governance DB (at `~/.hermes/data/loop-governance.db`)
8. **Prints** the decision and task so you can follow up with feedback

### Example

```
$ git commit -m "fix: nginx returns 0 for uninstalled"
📊  score-cycle: LOOP 🔄 (task=precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled, pass-pct=100)
[main abc1234] fix: nginx returns 0 for uninstalled
```

The cycle is now in the DB with `task_id = precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled`, `cycle_num = 1`.

---

## Installation

### One-liner (via cortex-update)

If you already have `cortex-update` installed, the hook is deployed automatically
on every update. To force immediate installation:

```bash
cortex-update --force-all
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
cp ~/hermes-cortex/src/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit
chmod +x ~/.hermes-cortex/hooks/pre-commit

# Set global hooks path
git config --global core.hooksPath ~/.hermes-cortex/hooks/
```

### Verify installation

```bash
git config --global core.hooksPath
# → /home/<user>/.hermes-cortex/hooks

ls ~/.hermes-cortex/hooks/
# → pre-commit  (pre-push also present if deployed)
```

Then test on any repo:

```bash
cd /tmp && mkdir test-hook && cd test-hook && git init
echo "hello" > test.txt && git add test.txt && git commit -m "test: hook works"
# → 📊  score-cycle: LOOP 🔄 ...
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

`SKIP_SCORE=1 git commit ...` skips the hook. This is **for emergencies only**.

Legitimate reasons to bypass:
- The `score-cycle` CLI itself needs to be repaired
- Loop-governance DB is locked or corrupted
- You're in the middle of a rebase conflict resolution

**The `SKIP_SCORE=1` bypass is not a workflow.** If you use it more than once
per month, something is wrong — fix the tooling, don't learn to live around it.

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
                    ┌──────────────────────┐
                    │   git config --global │
                    │   core.hooksPath      │
                    │   = ~/.hermes-cortex/ │
                    │   hooks/              │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
      ┌──────────┐      ┌──────────┐      ┌──────────┐
      │ repo A   │      │ repo B   │      │ repo C   │
      │ .git/    │      │ .git/    │      │ .git/    │
      │ hooks/   │      │ hooks/   │      │ hooks/   │
      │ (global) │      │ (global) │      │ (global) │
      └──────────┘      └──────────┘      └──────────┘
            │                  │                  │
            └──────────────────┼──────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │  pre-commit script   │
                    │  calls score-cycle   │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  loop-governance.db  │
                    │  ~/.hermes/data/     │
                    └──────────────────────┘
```

A single `core.hooksPath` setting in `~/.gitconfig` makes every repo use the
same hooks directory. No per-repo installation needed.

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
# If this fails, the score-cycle CLI or loop-governance setup is broken.
# Re-run: ~/hermes-cortex/src/loop-governance/setup.sh
```

### Per-repo hook overrides global
Some projects set `core.hooksPath` locally. Check:
```bash
git config --local core.hooksPath  # should be empty
git config core.hooksPath           # should show global path
```

### score-cycle not found
The hook prints a warning and exits cleanly (doesn't block the commit).
Install loop-governance tools:
```bash
bash ~/hermes-cortex/src/loop-governance/setup.sh
```

---

## Related

- [Agent Execution Contract, Rule #10](../AGENTS.md#10-score-every-change)
- `src/scripts/pre-commit-score` — the hook script
- `src/scripts/cortex-update.sh` — auto-deploys the hook via `install_precommit_hook()`
- `src/loop-governance/setup.sh` — installs `score-cycle` and `loop-feedback` CLI tools
