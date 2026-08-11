---
name: orch-skill-lifecycle
category: devops
description: "Unified daily skill lifecycle pipeline — collects lessons, evaluates quality, and upgrades skills/SOUL.md. Replaces skill-miner, harvest-lessons, skill-triage, soul-refinement, and agent-weekly-loop-eval."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Orch Skill Lifecycle — Unified Daily Pipeline

## Overview

Single daily cron (04:00 KST) that replaces 5 separate processes. Runs the full skill lifecycle end-to-end: **collect → evaluate → upgrade**.

The cron has `terminal` + `file` + `web` tool access. It reads agent data from the PGMQ bus (inbox_orchestrator queue — the shared orchestrator inbox) where each fleet agent's `agent-learning-collector` pushes structured reports every 6h.

## Replacements

| Old Cron | Fate | Absorbed Into |
|----------|------|---------------|
| `skill-miner` (Mon 06:00) | Removed | Collection + Evaluation |
| `skill-triage` (06:00/18:00) | Removed | Collection (bus reads) + Upgrade (upstream) |
| `harvest-lessons` (Mon 05:00) | Removed | Collection (session mining) |
| `agent-weekly-loop-eval` (Mon 09:00) | Removed | Evaluation (weekly deep) |
| `agent-daily-soul-refinement` (23:00) | Removed | Evaluation + Upgrade (SOUL.md) |

## Data Sources — Fleet Agents

This pipeline collects from ALL agents in the fleet. Each agent runs `agent-learning-collector` (no_agent, every 6h) which sends structured reports to the bus.

### Agent Data Collected

| Source | What | Collection Method |
|--------|------|-----------------|
| **Skills** | New/modified SKILL.md files since last report | Hash-based delta detection |
| **Lessons** | New lesson files in `~/brain/lessons/` | `session-mine mine --days 1 --auto` (bootstraps all history on first run, then incremental) |
| **Learnings (ad-hoc)** | Pending `.md` files in `~/brain/learnings/pending/` | File-based — agents write structured `.md` during sessions, moved to `sent/` after upload |
| **Sessions** | Total/recent session counts | SQLite query on Hermes session DB |
| **System** | Hostname, OS, Hermes version | Deterministic system query |

### Bus Message Format

The pipeline reads `inbox_orchestrator` PGMQ queue (the shared orchestrator inbox). Each agent sends a `Learning Report` every 6h via `agent-learning-collector`:

```
Subject: Learning Report: N skills, M lessons

━━━ Learning Report — {hostname} ━━━
Generated: {timestamp}
Type: full
Sessions: 142 total, 8 recent

== Skills (2 changed) ==
  [NEW] swap-refresh-logic (devops)
     Handles SwapCached double-count in health reports
  [MOD] session-cache-build (mlops)
     Added retry on empty results

== Lessons (1 new) ==
  • PG CTE materialization quirk
    Using WITH ... UPDATE ... RETURNING and WITH ... DELETE in the same
    CTE doesn't see the updated rows — fix by separating into two CTEs
```

(Legacy only — replaced by Learning Report above)

### Agent-Side Deployment

Each fleet agent (Gisu, Titus, Esther, Joseph, Kustos, Moses) runs:
- `agent-learning-collector` (no_agent, every 6h) — auto-discovers and reports
- No LLM on the agent side — fully deterministic
- Silent when nothing new (watchdog pattern)

## Pipeline Phases

### Phase 1 — Collection

Gather raw material from all sources:

1. **Bus reports** — Read `inbox_orchestrator` queue for Learning Reports from all fleet agents (agent-learning-collector, every 6h):
   - Skills delta (new/modified SKILL.md files)
   - Lessons delta (new files in ~/brain/lessons/)
   - Heartbeat (no changes, but agent is alive)
   - **⚠️ Data source (verified 2026-08-12):** the agent-message-handler
     early-archives Learning Reports within seconds of receipt and stages the
     full body to `~/.hermes-cortex/state/learning-reports/<agent>-<ts>.md`
     (so the queue reads depth 0 even with fresh reports). The staged files
     are the authoritative pipeline input — read the newest per-agent file
     there, not the queue. For archived bus messages use
     `/api/pgmq/archives/{queue}?limit=N&since_minutes=10080` (default
     `since_minutes=60` hides everything older than an hour).
2. **Git log** — Check recent commits for self-improvement patterns needing broader consolidation
3. **Skill inventory** — Scan repo skills for stale/modified files
5. **Doctor health check** — Run `cortex-doctor.py --quiet` and check for:
   - ❌ Crons missing → stale entries in uninstall arrays (self-healing candidate)
   - ❌ Orch crons → orchestrator cron issue
   - ❌ Script integrity → missing deployed scripts
   - **Cross-reference** — Compare reports across agents for consolidation candidates

8. **Session compliance audit** — Scan the orchestrator's recent session transcripts for self-improvement signals:
   - User corrections: search for patterns where the user corrected Moses ("you should have", "don't ask", "fix permanently", "never ask me", "CODIFY THIS")
   - Principle violations: search for Moses asking "want me to", "should I", or "do you want" about obvious fixes (Principle 12 violation)
   - Session-start violations: check if `skill_view('task-start')` was called in the first 3 tool calls
   - Governance violations: check if `begin_change` was used before any file writes
   
   **Collection method:** `session_search(query='correction|"never ask"|"fix permanently"|"CODIFY THIS"', limit=10)` to find recent sessions with user corrections. For each hit, extract:
   - What was the correction?
   - Which principle was violated?
   - Was a guardrail already added?
   - If no guardrail → create HIGH-priority evaluation item

   **Output format:**
   ```
   Session compliance: N correction(s) found
     - [UNGUARDED] Principle 12 violation: asked "want me to..." instead of fixing
     - [GUARDED]   task-start not loaded at session start (guardrail added previously)
   ```

6. **Skill inventory scan** — Check all skills under `~/.hermes/skills/`:
   - List all SKILL.md files with modification dates
   - Check for stale references (paths, commands, URLs that no longer exist)

7. **Pre-commit trail** — Check recent git commits in `~/hermes-cortex/` for:
   - Self-improvement patches that may need broader consolidation
   - Patterns across multiple commits

**Output:** A compiled list of items to evaluate. Each item has:
```
{item_type: "lesson"|"bus_report"|"stale_ref"|"consolidation_candidate",
 source: "session"|"bus"|"inventory"|"git",
 content: "...",
 agent: "moses"|"fleet_agent_name",
 priority: high|medium|low}
```

### Phase 2 — Evaluation

For each collected item, classify and decide:

0. **Ledger intake (F-006)** — Read pending learnings from the fleet ledger
   (the F-001 `learnings` schema on the bus Postgres — orchestrators only):
   ```bash
   learning-ledger.py list --status pending
   ```
   Each row is an evaluation item (`item_type: "ledger"`, `source: "ledger"`,
   content/agent from the row). Fold them into the classification below.
   After deciding a learning's fate, write the disposition back — the ONLY
   UPDATE path, party L-1 (via `learnings.set_status()`, never direct UPDATE):
   - **evaluated** → `learning-ledger.py set-status <id> evaluated [--impact N]`
   - **applied** (after the skill/SOUL edit actually lands) →
     `learning-ledger.py set-status <id> applied [--impact N]`
   - **retired** (dup/stale/low-value) →
     `learning-ledger.py set-status <id> retired [--impact N]`
   - `--impact` revises the collector's score (-3..+3) when evaluation
     disagrees; omit it to keep the captured score. Do NOT mark anything
     you did not process — leave it pending for the next run.

1. **Classification** — Is this:
   - **New lesson** → skill pitfall / step / warning to add
   - **Reinforcement** → existing skill already covers it, strengthen
   - **Principle** → belongs in SOUL.md, not a skill
   - **New skill** → fleet agent discovered something new
   - **Consolidation** → multiple skills overlap, should merge
   - **Stale** → skill references dead path/command, needs pruning

2. **Dedup** — Before acting, check:
   - Does this exact lesson already exist in a skill?
   - Is there a skill with the same name/content already?
   - Has this been applied before? (check git log, skill decisions state)

3. **Priority** — Apply the correct action:
   - **HIGH** — Broken command, security issue, stale cron → fix immediately
   - **MEDIUM** — Workflow improvement, new pitfall → fix during this run
   - **LOW** — Nice-to-have, speculative → defer or archive

4. **Weekly deep evaluation** (if today is Monday):
   - Full consolidation pass: check ALL skills for cross-overlap
   - Staleness scan: check every skill's paths, commands, and references
   - Pruning: flag skills with zero usage or that have been superceded

### Phase 3 — Upgrade

Execute all approved actions:

> 🔒 **FENCE-SAFETY RULE (before ANY skill edit):** run the fence-balance check on
> the target file first — count lines that START with a triple-backtick fence
> (the doctor's `check_skill_fences` does this); an odd count = unbalanced.
> **Never** "remove stray fences", "clean up backticks",
> or "fix markdown" on a file that currently scans BALANCED — that is exactly the
> destructive pattern that corrupted change-test-loop/SKILL.md 5+ times. Only fix
> a file verified UNBALANCED, remove precisely the stray line, and re-verify even.
> `git pull --ff-only` before any edit (fresh state — a peer may have landed the
> fix already; never re-implement or step on concurrent work).

1. **Patch existing skill** — `skill_manage(action='patch', ...)` with new pitfall, corrected step, updated path
2. **Create new skill** — `skill_manage(action='create', ...)` for genuinely new discoveries (from fleet or own work)
3. **Merge skills** — Read both, compose unified SKILL.md, delete old
4. **Prune stale skills** — `skill_manage(action='delete', ...)` with `absorbed_into=""` for truly dead skills
5. **SOUL.md update** — Append principle changes to `~/.hermes/SOUL.md` with `<!-- Added YYYY-MM-DD -->`
6. **Upstream new skills to repo** — For fleet-submitted skills:
   - ⚠️ **Stub guard (2026-08-05):** before upstreaming ANY fleet skill, read
     the source content (the deployed SKILL.md on the reporting host, or the
     collector's report). If the body contains `(content unavailable)` or
     `[SKILL_PRUNED]` — i.e. the frontmatter survived but the body is a
     compression/pruning placeholder — DO NOT upstream it. Flag it for
     restore (re-install the full version from the Skills Hub, or author the
     content) and list it as a stub in the run report. Never commit a
     placeholder body to the repo; that is how 28 marketing skills became
     stubs fleet-wide (auto-upstream 8587b511, Jul 17).
   - Create `hermes-cortex/skills/<category>/<name>/SKILL.md`
   - `git add`, commit, push
7. **Self-heal stale expected lists** — If doctor found ❌ Crons missing:
   - Identify which cron names are in the uninstall arrays of `install-crons.sh` or `install-orch-crons.sh` but have no matching live cron
   - Remove those names from the uninstall arrays
   - The doctor reads these arrays as its expected cron list — a name there with no matching live cron causes a false ❌
   - Commit and push the fix
8. **Archive processed bus messages** — Clean inbox_orchestrator for processed skill reports

### Verification

After all changes:
1. Confirm skills are readable: `skill_view(name)` for each changed skill
2. Check syntax: `skill_manage(action='patch')` returns a diff — verify it looks correct
3. **Fence balance on every changed SKILL.md** — even fence count, before commit. Any file with an odd count blocks the commit anyway (pre-commit gate), but verify BEFORE staging, not after.
4. Verify SOUL.md is valid markdown
5. Run `cronjob action='list'` to confirm old crons are gone
6. If Monday: verify the session cache exists and is current

## Output Format

Produce a structured report each run:

```
orch-skill-lifecycle (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Collection:
- Sessions mined: 12 (3 corrections, 1 discovery)
- Bus: 2 Skill Report messages from fleet
- Skills scanned: 142 files, 2 stale refs found
- Pre-commit: 1 consolidation pattern detected

Phase 2 — Evaluation:
- 4 items classified: 3 skill patches, 1 SOUL.md principle
- 1 duplicate filtered (already in skill 'agent-flow')
- 2 stale refs: archived for Monday deep eval
- Ledger: 3 pending learnings processed (1 applied, 1 evaluated, 1 retired)

Phase 3 — Upgrade:
- Patched: agent-flow (pitfall section), cortex-bus (new step)
- SOUL.md: 1 principle added
- Upstreamed: 1 new skill from fleet (swap-refresh)
- Ledger: dispositions written via learning-ledger.py set-status
- Bus: 2 messages archived
- Git: committed + pushed

Result: 3 skills updated, 1 upstreamed, 1 SOUL.md entry.
```

## Schedule

- **Daily (04:00 KST)** — Full pipeline with light evaluation
- **Monday deep eval** — Additional consolidation + pruning + staleness pass

## Pitfalls

- **Sender whitelist enforced (71d36cc5, 2026-08-10)** → `orch-skill-report-process.py`
  rejects reports from NON-fleet senders. An unregistered host (LAM2.local) still
  running the retired `collect-skills` cron flooded `inbox_orchestrator` with 76
  duplicate "Skill Report: N custom skills" messages over days — nothing consumed
  them, drowning real agent proposals (all 78 archived). When a legitimate fleet
  report seems missing, check the sender is in the whitelist (Gisu, Titus, Esther,
  Joseph, Kustos, Moses) and that no retired host-side cron is still pushing the
  legacy Skill Report format. The pipeline consumes **Learning Report** messages,
  not legacy Skill Reports.
- **Don't patch the same skill twice in one run** — deduplicate before acting
- **Don't upstream fleet skills that already exist** — check repo + Hermes bundle
- **Don't modify SOUL.md for workflow lessons** — skills are for workflow, SOUL.md is for principles
- **Don't skip verification** — a bad skill patch breaks every agent that loads it
- **Confidence scoring**: HIGH = verified with real commands, MEDIUM = manual analysis, LOW = untested — do not release LOW
- **Archive bus messages after successful upstream, not before** — if push fails, message stays in queue for retry
