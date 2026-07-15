---
name: loop-governance
version: 1.0.0
category: devops
description: "Loop Governance system: score-cycle, loop-feedback, auto-apply, skill-miner, session-cache, and evaluation pipeline. Tracks code changes via scored cycles, auto-applies low-risk patches, and mines skills from scored data."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [scoring, governance, evaluation, tdd, loop, feedback]
---

# Loop Governance

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

**Structural enforcement layers (hard blocks, listed in priority order):**

1. **Hermes Plugin** (primary) — `~/.hermes/plugins/governance-enforcer/` uses the `pre_tool_call` plugin hook to intercept ALL tool calls before they execute. See the [`governance-plugin-implementation.md`](skill_view?name=loop-governance&file_path=references/governance-plugin-implementation.md) reference for full API docs, block matrix, and fleet installation. Key facts:
   - Blocks `write_file`, `patch`, `terminal` write commands, `cronjob` create/update/remove, `skill_manage` create/edit/delete without an active governance lock
   - Fires at the Hermes runtime level — the agent CANNOT bypass it mid-session
   - Installed via `ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/` then `/reset`
   - A `README.md` with full documentation lives at `~/.hermes/plugins/governance-enforcer/README.md`

2. **Pre-commit hook** (secondary) — global `core.hooksPath ~/.hermes-cortex/hooks/` auto-scores every `git commit`. Does NOT block commits (that is the plugin's job), but ensures the scoring DB is populated.

3. **Cron auditor** (reactive) — `governance-auditor` cron (every 6h) scans for unscored changes and reports findings.

4. **SOUL.md directive** (identity layer) — the loop governance principle in SOUL.md is the final backstop.

**IMPORTANT CORRECTION:** The `loop-gov-mcp.py` MCP server does NOT block Hermes write tools (`write_file`, `patch`, `terminal`, etc.). MCP servers only *provide* tools — they do not intercept or block Hermes built-in tools. The `begin_change()` / `end_change()` MCP tools create and release governance lock files, but the actual blocking must happen at the plugin level. If the plugin is not installed, there is NO structural enforcement — only self-discipline.

**Lock files are per-repo:** Each git repo on the same machine gets its own lock at `~/.hermes-cortex/state/.governance-{repo-slug}.json`. A lock open in `hermes-cortex` doesn't affect work in `project-b`. See the governance-plugin-implementation.md reference for details.

## Tools

All tools are symlinked at `~/.local/bin/`:

| Tool | Purpose |
|------|---------|
| `score-cycle` | Log a change cycle: task, code file, pass rate |
| `loop-feedback` | Accept or override a scored cycle's decision |
| `auto-apply` | Auto-apply low-risk config patches from evaluated cycles |
| `loop-config` | View/set runtime config (weights, thresholds) |
| `session-cache-build` | Build/session search cache |
| `skill-miner` | Mine scored cycles for reusable skill patterns |

## Weekly Evaluation Pipeline

1. **Pull scored cycles** from the last 7 days via the loop evaluator
2. **Run skill-miner** to extract reusable patterns from scored data
3. **Run auto-apply** to apply low-risk config changes
4. **Report results**: cycles scored, skills mined, patches applied

## Session Cache Setup

The session cache provides fast pre-work context lookups via `cache_search()`. 
On first use (or when `Cache DB not found`), it must be initialized:

```bash
PYTHONPATH=~/.hermes/scripts python3 ~/hermes-cortex/core/governance/session_cache.py build
```

This embeds session files, loop DB cycles, and skills using `nomic-embed-text:v1.5` 
via Ollama. Requires:

- Ollama running with `nomic-embed-text:v1.5` pulled (261MB model)
- Session files at `~/.hermes-cortex/sessions/`
- Write access to `~/.hermes/data/` (creates `session-embeddings.db`)

**Pitfall — constrained machines:** On machines with limited RAM (~2GB free),
the build may be slow or fail. The embedding model adds memory pressure to the 
already-loaded `qwen2.5-coder:3b`. Build during low-load periods or accept that
`cache_search` will be unavailable (Phase 1 of the Agent Workflow becomes a 
no-op, but Phase 3 still applies — the habit of checking matters more than the DB).

**Pitfall — import path:** The script needs `hermes_models.py` from `~/.hermes/scripts/`
on `PYTHONPATH`. Running from the repo directory (`~/hermes-cortex/core/governance/`) 
may fail with `ModuleNotFoundError: No module named 'hermes_models'`. Fix:
```bash
PYTHONPATH=/home/esther/.hermes/scripts python3 core/governance/session_cache.py build
```

## Agent Workflow (MANDATORY — applies every change)

Every code, config, or cron change REQUIRES a governance cycle. This is a three-phase sequence:

```
Phase 1 — Pre-work:  cache_search(query="<what I am about to do>")
Phase 2 — The change: patch / write_file / cronjob / memory add
Phase 3 — Post-work:  cycle_query(task_id="<task>") + feedback_accept() or feedback_override()
```

This applies to **every** `patch`, `write_file`, `cronjob`, `memory` write — any durable state change. No exceptions.

**Purpose:** The cache_search prevents rework by surfacing prior context. The cycle + feedback feeds the scoring system so it can learn which patterns produce good outcomes.

**If session-cache is unavailable** (cache DB not built): Build it now with `session-cache-build build`. Do not skip governance because the cache is missing — build it first.

### Post-work: finding auto-created cycles

Cycles are **auto-created** by the system when you use state-changing tools (patch, write_file, cronjob, memory). You do NOT create them manually.

After each change, find and evaluate the auto-created cycle:

1. Call `cycle_query(task_id="<task>")` — search for the cycle
2. Evaluate the score — does the automated decision match what you'd choose?
3. Call `feedback_accept(cycle_id=N)` if the decision was appropriate
4. Call `feedback_override(cycle_id=N, correct_decision=LOOP|STOP|MOVE_ON, note="...")` if wrong

**If no cycle was auto-created:** Known limitation — `patch` under active lock doesn't auto-create cycles. Follow the force-clear protocol:
   - Call `end_change(task_id)` — it will reject with "no scored cycle found"
   - **Confess clearly**: "end_change rejected — no cycle auto-created for this tool type. Force-clearing lock."
   - `rm -f ~/.hermes-cortex/state/.governance-$(basename $(git rev-parse --show-toplevel 2>/dev/null || echo 'generic')).json`
   - Never silently force-clear without calling `end_change` first.

**Phase 3 is about awareness, not bureaucracy.** If you can't find a cycle, the system still knows you followed the pattern. The habit matters more than the DB entry.

### Per-change scoring, not per-session

Each logical change gets its **own** cycle. Batch-scoring a whole session is not acceptable — the system needs per-change granularity.

### Pitfall: Read-only sessions that turn into writes — always cache_search before the first write

A session starting as read-only verification (reading scripts, checking files) can discover a bug mid-way. The moment you switch from read to write, the governance obligation activates. **Pause before the first `patch`/`write_file`/`cronjob`/`memory` call** and run `cache_search(query="<the bug you found>")`, then proceed with the fix, then query `cycle_query` and provide feedback.

If you skip this, the user will notice — they will ask "Have you done any loop governance?" Do not defend or explain. Accept the miss immediately and run the steps.

**Concrete example from production (July 2026, Esther):**
A session started as read-only verification: checking scripts, git diffs, Ollama status, cron health. No writes planned — the governing assumption was "just checking." Mid-way a bug was discovered: `cortex-update.sh` could self-destruct when the deploy target path equals `~/.hermes`. The agenda shifted to fixing it — two `patch` calls, a `write_file`, and a memory batch followed.

**What went wrong:** The governance obligation activated at the first `patch`, but the agent never paused to do the cache_search. The read-only velocity carried forward. The user noticed and asked "Have you done any loop governance?" — a clear signal the pattern was missed.

**The fix:** When a read-only session uncovers a write-worthy bug, treat the transition as a explicit state change:
- Pause before the first write
- Run `cache_search(query="<the bug you found>")`
- Then proceed with the fix
- Query `cycle_query` after the change and provide feedback

### Pitfall: Stale task_id matching — `end_change` matches across all dates

`end_change` looks up cycles by `task_id` with no date filter. If you reuse a bare task_id from a previous session (e.g. `hermes-cortex-pull-merge` from Jul 2), `end_change` finds that old cycle and releases the lock — **no new cycle is created for today's work.** The scoring-activity-watchdog then correctly flags 0 cycles for the day.

**Prevention:** Date-qualify every task_id: `hermes-cortex-pull-merge-20260704`. This garantees `end_change` only matches a cycle you create in the current session.

## CLI Tools (for batch ops and cron jobs)

Agents use the MCP tools above in their workflow. The CLI tools are for system-level operations, cron jobs, and debugging:

```
score-cycle --task "<task-id>" --cycle <N> --code-file <path> --pass-pct <rate>
loop-feedback accept <N> --note "..."
loop-feedback override <N> --decision loop|stop|move_on --note "..."
auto-apply --dry-run          # preview without applying
auto-apply                    # apply low-risk patches
loop-config                   # show current config
session-cache-build build     # rebuild session cache
skill-miner                   # mine skills from scored cycles
```

## Scoring

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Completeness | 40% | How complete the change is |
| Quality | 30% | Code quality, tests, documentation |
| Progress | 30% | Progress toward goal |

Thresholds: stop ≥ 8.0, loop ≥ 5.0, move_on ≥ 3.0, no_progress < 2.0 (3 strikes).

## Paths

- Scripts: `~/.hermes-cortex/tools/loop-governance/`
- CLI wrappers: `~/.local/bin/{score-cycle,loop-feedback,auto-apply,loop-config,session-cache-build,skill-miner}`
- DB: `~/.hermes-cortex/data/loop-governance.db`
- Config: `~/.hermes-cortex/data/loop-governance-config.json`
