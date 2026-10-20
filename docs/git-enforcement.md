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
- **pre-push** — five checks before allowing a push:
 1. **Governance lock** — requires an active `begin_change()` session
 2. **Review receipt** — a range touching an always-review path needs a CLEAN review receipt for THAT range (tip+base). Ordinary commits are exempt. See `docs/review-receipt-gate.md`
 3. **Syntax check** — parses every changed `.py` and `.sh` file (py_compile/bash -n)
 4. **Doc coverage** — warns if code/config changes without `.md` changes
 5. **Pull-before-push** — ensures local `main` isn't behind `origin/main`

They're part of the Agent Execution Contract (rules #10 and #13) and apply to every agent and human working on `hermes-cortex`.

---

## The Two Hooks

### `pre-commit` (rule #10: Score Every Change)

Source: `ops/scripts/pre-commit-score`

Runs `score-cycle` on staged changes for **automatic DB logging**. Enforcement of the governance lock is handled by the MCP server — this hook just ensures a cycle is recorded for every commit.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0  | Scored (or skipped, or score-cycle absent) | Commit proceeds |
| 1  | `score-cycle` failed unrecoverably | Check loop-governance setup |

### `pre-push` (rules #13 + verification gate)

Source: `ops/scripts/pre-push-pull`

**Workflow order:**

1. Make changes under governance (begin_change → work)
2. **Update documentation** — docs, AGENTS.md, skills that other agents consume
3. Push — the hook enforces these checks:

  | # | Check | What it does |
  |---|-------|-------------|
  | 1 | Governance lock | No active `begin_change()` session for this repo — **unless** a CLEAN review receipt covers the unpushed range, which is the same accountability (written by a permitted close, bound to the content) and removes the need for a second, no-content lock-carrier cycle. Only a lone `git push` qualifies (never `--no-verify` or a compound). See `docs/review-receipt-gate.md`. |
  | 2 | Review receipt | A range touching an always-review path (`ops/scripts/lib/always-review-paths.txt`) must carry a CLEAN receipt for that exact range — tip AND base. Written automatically when a cycle closes. Verify with `ops/scripts/lib/review-receipt-check.py <receipt> <tip> <base>`. See `docs/review-receipt-gate.md`. |
  | 3 | Syntax check | Parses every changed `.py` (py_compile) and `.sh` (bash -n) file at push time. Cannot be skipped — the hook runs the checker itself. |
  | 4 | Doc coverage | Warns when code/config files change without a corresponding `.md` change. Soft warning — doesn't block, but reminds agents to update docs. |
  | 5 | Pull-before-push | Local `main` is behind `origin/main` |

  All checks run automatically at push time. No marker files, no `touch` commands.

| Exit | Meaning | Next step |
|------|---------|-----------|
| 0  | All checks passed + marker consumed | Push proceeds |
| 1  | Any check failed | Fix the issue shown in the error message |

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

The installer deploys the source scripts to `~/.hermes-cortex/scripts/` and `cortex-update.sh` creates symlinks from `~/.hermes-cortex/hooks/` to those scripts. This means git pull + cortex-update keeps hooks current without manual re-install.

---

## Bypass Mechanisms

There is **no sanctioned bypass**. The pre-commit hook runs scoring **and** the mandatory adversarial verification gate (A2 default, A4 for security/guard/hook/enforcer files) on every staged script. `--no-verify` is a **logged, audited bypass** (`agent-no-verify-audit` cron) — it is not a conscious choice, it is an audit event, and it must never be used to ship a hook-rejected change. Pre-commit `SKIP_SCORE=1`, `SKIP_ADVERSARIAL`, and pre-push `SKIP_PRE_PUSH=1` bypass flags have all been removed — no env-var bypasses.

**When the hook blocks you:** fix the finding (the gate prints what it found), then commit normally through the hook. If the scoring stack itself is broken, repair via the sanctioned path: `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`.

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
| Hook not running at all | Hook not symlinked into `~/.hermes-cortex/hooks/` | Re-run `cortex-update.sh ` |
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

---

## Pinned Repo Hooks — Refresh + Guard Carve-Out

> **Merged from `docs/pinned-repo-hooks.md` on 2026-10-20.** These two documents covered two halves of one topic; the section below is the half that lived in `docs/pinned-repo-hooks.md`. That source path is preserved in git history and recorded in [`docs/older/README.md`](older/README.md) — no content was dropped in the merge.

**Status:** Shipped 2026-08-05 (`527e651a`), Titus audit follow-up.

### Problem

`pin_repos_with_own_hooks()` (cortex-update.sh) preserves repos that ship
their own git hooks by setting a repo-local `core.hooksPath` to the repo's
own `.git/hooks`. It pinned the path but **never refreshed the hook files** —
pinned repos kept stale copies (Jul 24 generation) that predated the
mandatory adversarial gate (faa0e929/72d6cdc3). Commits in those repos got
score-logging but **no adversarial verification** (Titus audit 2026-08-05: 9
repos on macOS, `grep -c adversarial = 0`).

### Fix (three parts + one critical addition)

1. **`refresh_pinned_hook_files()`** — after pinning, copies the 4 cortex
   hooks (pre-commit-score, pre-push-pull, post-commit-audit, post-push-audit)
   from deployed source into the repo's own hooks dir. Only files carrying
   the cortex banner (`Git <type> hook`, ASCII match for macOS locale
   safety) are refreshed; **foreign hooks are preserved** (vllm pre-commit
   framework shim, bespoke deploy hooks). Missing hook files get the gate
   installed.

2. **Crawl exclusions** — `*/Library/*` and `*/node_modules/*` pruned from
   the pin crawl: macOS `~/Library/Containers` is a ~1m20s crawl per deploy
   (Aug 4 incident wedged it 5h08m); node_modules holds thousands of vendored
   `.git` dirs that must never be pinned.

3. **Doctor check `Pinned hooks fresh`** (7c) — for every repo with a local
   `core.hooksPath`, compares each cortex hook file against the deployed
   source with `_content_md5()` (strips the SOURCE header). FAIL on drift
   with remediation hint `cortex-update.sh --force`. Foreign hooks skipped.

4. **⚠️ Guard carve-out (critical — discovered during verify)** — the
   deployed pre-commit/pre-push hooks fail CLOSED when `core.hooksPath !=
   ~/.hermes-cortex/hooks` (5ab54547). Pinned repos exist precisely because
   their hooksPath points at their own dir — refreshing the full hooks into
   them would have blocked **every commit**. The guard now passes when the
   hooks dir carries any cortex-managed hook (governance IS running there);
   it still fails closed when hooksPath points at a dir with no cortex hooks
   (the original bypass tripwire).

### Why the carve-out is safe

The guard's own comment states its purpose: *"The REAL danger is when
hooksPath points elsewhere entirely, meaning NO governance hooks run at
all."* A pinned repo with refreshed cortex hooks HAS governance running —
the carve-out accepts exactly that state. A repo pointing hooksPath at an
attacker-controlled dir with no cortex hooks still blocks.

### Verify (all three, done on Linux 2026-08-05)

1. Scratch repo with stale cortex hook → refreshed to byte-match deployed,
   adversarial gate present (10 hits), commit passes the hooksPath guard
2. Repo with foreign vllm shim → refresh skips it, hash unchanged
3. Doctor: FAIL on stale (`36f9a960 != 13bbebff`) → refresh → PASS
   ("all 4 pinned hook file(s) match deployed source")

### Rollout

Deployed via `cortex-update.sh`; the refresh runs automatically on every
deploy for all pinned repos on every host (Linux + macOS). No manual action
per repo.

---

## Pre-Commit Scoring Hook

> **Merged from `docs/pre-commit-scoring.md` on 2026-10-20.** These two documents covered two halves of one topic; the section below is the half that lived in `docs/pre-commit-scoring.md`. That source path is preserved in git history and recorded in [`docs/older/README.md`](older/README.md) — no content was dropped in the merge.

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

### Secondary Logger — the MCP Server Is Primary

The pre-commit hook is now a **secondary logger**, not the primary enforcement mechanism.

**Primary enforcement is at the MCP tool level.** The `loop-gov-mcp.py` server blocks `write_file`, `patch`, `terminal`, `skill_manage`, and `cronjob` unless an active governance lock exists. You cannot write a file or create a cron without calling `begin_change()` first. This catches ALL changes — git-tracked or not, config-only, deployments, sudoers edits — at the Hermes tool level, before anything reaches disk.

This hook adds **automatic scoring on every `git commit`** so cycles get logged to the DB for data collection and self-improvement. It's optional for enforcement (the MCP server already handled that) but valuable for keeping the scoring DB populated without manual effort.

### How It Works

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

#### Example

```
$ git commit -m "fix: nginx returns 0 for uninstalled"
📊 score-cycle: LOOP 🔄 (task=precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled, pass-pct=100)
[main abc1234] fix: nginx returns 0 for uninstalled
```

The cycle is now in the DB with `task_id = precommit-hermes-cortex-main/fix-nginx-returns-0-for-uninstalled`, `cycle_num = 1`.

---

### Installation

#### One-liner (via cortex-update)

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

#### Manual install

```bash
## Deploy the hook script
mkdir -p ~/.hermes-cortex/hooks
cp ~/hermes-cortex/ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit
chmod +x ~/.hermes-cortex/hooks/pre-commit

## Set global hooks path
git config --global core.hooksPath ~/.hermes-cortex/hooks/
```

#### Verify installation

```bash
git config --global core.hooksPath
## → /home/<user>/.hermes-cortex/hooks

ls ~/.hermes-cortex/hooks/
## → pre-commit (pre-push also present if deployed)
```

Then test on any repo:

```bash
cd /tmp && mkdir test-hook && cd test-hook && git init
echo "hello" > test.txt && git add test.txt && git commit -m "test: hook works"
## → 📊 score-cycle: LOOP 🔄 ...
rm -rf /tmp/test-hook
```

---

### What the Hook Does NOT Do

| Concern | How it's handled |
|---------|-----------------|
| **Block commits** | The hook only blocks if `score-cycle` itself has an unrecoverable error. Normal LOOP/STOP/MOVE_ON decisions never block. |
| **Enforce feedback** | The hook creates the cycle but doesn't provide `feedback_accept`/`override`. That's the agent's (or human's) job — follow up with `loop-feedback accept <id>` or `loop-feedback override <id> --note "..."`. |
| **Run tests** | If `pytest.ini` is present, the hook runs the test suite and calculates a pass rate. If no tests exist, it assumes `pass-pct 100`. |
| **Handle binary/lock files** | Binary files (`.png`, `.jpg`, `.ico`) and lock files (`package-lock.json`, `yarn.lock`, `.lock`) are automatically excluded. |

---

### Bypassing the Hook

There is **no bypass** — `SKIP_SCORE=1` has been removed, and `git commit --no-verify` is a **logged, audited bypass** (see `agent-no-verify-audit` cron), never a workflow. The pre-commit hook also runs the **mandatory adversarial verification gate** on every staged script (A2 default, A4 for security/guard/hook/enforcer files) — a hook-rejected change must be **fixed, not bypassed**.

When the scoring stack itself needs repair, fix it via the sanctioned path (`cortex-update.sh` — it deploys the scorer on Linux and macOS), then commit normally through the hook. If you are mid-rebase-conflict-resolution, resolve the conflict — rebase replays do not run pre-commit, so the commit will already pass; there is no reason to bypass.

**The bypass is not a workflow.** If `--no-verify` appears more than once per month in the audit log, something is wrong — fix the tooling, don't learn to live around it.

---

### Closing the Feedback Loop

The hook creates the cycle. You still need to provide feedback so the governance
system can learn whether each cycle was good or bad.

#### Via MCP (Hermes agents)

```python
## Find the cycle
mcp__loop_governance__cycle_query(task_id="precommit-hermes-cortex-main/nginx-returns-0-for-uninstalled")

## Accept it (correct decision)
mcp__loop_governance__feedback_accept(cycle_id=122, note="nginx health fix — 0 for uninstalled")

## Or override (wrong decision)
mcp__loop_governance__feedback_override(cycle_id=122, correct_decision="STOP", note="This change was complete, should have been STOP")
```

#### Via CLI (scripts, pre-commit hooks, shell)

```bash
loop-feedback accept 122 --note "nginx health fix — 0 for uninstalled"
loop-feedback override 122 --note "Complete change, should STOP" --correct-decision STOP
```

---

### Architecture

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
> (client-alpha, etc.) that have **no `ops/` tree and no `.hermes-cortex/`**
> inside them. A hook that resolves a tool via `$REPO_ROOT/ops/...` (the repo
> being committed IN) breaks every commit there — regression `faa0e929`, fix
> `72d6cdc3` (2026-08-04). Hooks must resolve shared tools with a candidate
> loop: repo-local first, then the canonically-deployed copy at
> `$HOME/.hermes-cortex/scripts/` (registered by cortex-update.sh on both
> Linux and macOS). See `enforcement-change-safety` Rule 6.

---

### Troubleshooting

#### Hook doesn't fire
```bash
## Check hooksPath is set
git config --global core.hooksPath
## Should output: /home/<user>/.hermes-cortex/hooks

## Check hook file exists
ls -la ~/.hermes-cortex/hooks/pre-commit

## Check it's executable
test -x ~/.hermes-cortex/hooks/pre-commit && echo "executable" || echo "not executable"
```

#### Cycle not created (hook says LOOP but DB empty)
```bash
## Manually test score-cycle
score-cycle --task "test-diagnostic" --cycle 1 --code-file /dev/null --json
## score-cycle is deprecated — MCP-based governance in use instead.
```

#### Per-repo hook overrides global
Some projects set `core.hooksPath` locally. Check:
```bash
git config --local core.hooksPath # should be empty
git config core.hooksPath      # should show global path
```

#### score-cycle not found
The hook **blocks the commit** (exit 1 — fail closed). Scoring is part of the
enforcement chain: a commit without a cycle record is invisible to governance.
Fix by running `cortex-update.sh` to deploy the scorer (installs
`~/.hermes-cortex/tools/loop-governance/score_cycle.py` on Linux and macOS),
then re-commit. Do NOT use `--no-verify`.

---

### Related

- [Adoption Enforcement (loop-governance skill)](../skills/devops/loop-governance/SKILL.md#section-adoption-enforcement) — the four-layer enforcement model
- `ops/scripts/pre-commit-score` — the hook script
- `mcp-servers/loop-gov-mcp.py` — the primary enforcer MCP server
- `ops/scripts/cortex-update.sh` — deploys the hook via `install_precommit_hook()`
- `core/governance/setup.sh` — legacy CLI installer (not deployed; MCP-based governance replaces CLI tools). The scorer stack (`score_cycle.py` etc.) IS deployed to `tools/loop-governance/` by `cortex-update.sh` and invoked by the pre-commit hook.
