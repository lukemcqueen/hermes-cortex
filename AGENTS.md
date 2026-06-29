# Agent Guidelines — Hermes Cortex

This file is read by many agent tools (Claude Code, Copilot, Codex, Hermes, etc.)
on session start. It orients any agent working on this repo.

> **🪪 Scope:** This file serves two audiences:
> - **General agents** — the Architecture Principles, Agent Execution Contract, and Structured Development Pipeline below are universal to Hermes Cortex and recommended for every agent.
> - **Luke's deployment (Moses server)** — sections marked with a `⚡` tag are specific to Luke's multi-machine, multi-agent orchestration setup. They describe how Moses (the orchestrator agent) coordinates with peer agents Titus, Gisu, and Joseph. If you are not running Luke's setup, treat these as examples you can adapt.
>
> Everything unmarked is general Hermes Cortex guidance — apply it to any project using this repo.

## What This Repo Does

Hermes Cortex is a **public installer and skill set** for
[Hermes Agent](https://hermes-agent.nousresearch.com). A fresh install gets:

- **Ollama** — local LLM server for free embeddings
- **Bun + gbrain** — persistent knowledge brain (PGLite, zero-config)
- **Langfuse** — LLM trace evaluation and scoring
- **Cortex Dashboard** — companion dashboard for Langfuse + system health
- **Brain dirs** — MECE-organized knowledge sources per user
- **gbrain sync daemon** — automatic 2-minute sync (autopilot preferred; sync-watch fallback if absent)
- **Hermes plugin** — `/brain` slash command for knowledge queries
- **Utility scripts** — heartbeat, memory sync, system health, LLM scoring

## Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Troubleshooting, guides, templates, SECURITY.md |
| `docs/templates/` | Seed MEMORY.md, USER.md, brain .gitignore |
| `install.sh` | Single-command installer, 27 steps (idempotent) |
| `deploy/` | Langfuse + ClickHouse deployment (docker-compose, configs, README) |
| `deploy/docker-compose.langfuse.yml` | Langfuse v3.200.0 with ClickHouse, MinIO, Redis |
| `deploy/README-langfuse-clickhouse.md` | **📘 Start here** — Langfuse setup, ClickHouse crash fixes, Hermes wiring |
| `.hermes-cortex/sessions/current.md` | Active session state — branch, commits, task context |
| `.hermes-cortex/sessions/archive/` | Timestamped session snapshots |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `.hermes-cortex/memory/` | Per-user agent memory (gitignored — each dev has their own) |
| `agent-inbox-private/` | Dedicated inbox repo — all agent messages (git-backed) |
| `.gitignore` | Excludes .env*, *.pem, *.key, state.db, .hermes/, .hermes-cortex/memory/ |

## Cortex Project Directory Convention

This repo uses `.hermes-cortex/` for agent infrastructure, keeping the root
focused on source code and public docs. If you use Hermes Agent with this
repo, agents will check for `.hermes-cortex/` first and fall back to repo
root if absent.

```
project-root/
├── .hermes-cortex/           # Agent infrastructure (hidden, near code)
│   ├── sessions/
│   │   ├── current.md        # Active session (cron updates this)
│   │   └── archive/          # Timestamped session snapshots
│   ├── memory/               # Gitignored — per-user MEMORY.md, USER.md
│   ├── skills/               # Tracked — project-specific Hermes skills
│   └── .gitkeep
├── AGENTS.md                 # Stays at root — tool convention
└── docs/                     # Stays at root — team docs
```

Three-layer data model:

| Layer | Location | Content | Update cadence |
|-------|----------|---------|---------------|
| Hot session | `.hermes-cortex/sessions/current.md` | Branch, recent commits, task context | Every 30-120 min (cron) |
| Agent memory | `.hermes-cortex/memory/` | Compact pointers, user profile | Every session |
| Durable knowledge | `~/brain/<project>/` | Decisions, recipes, lessons | Weekly / as-needed |

## Architecture Principles

- **Two-repo system:** This public repo (open-source, MIT) + a private repo for personal config, secrets, and `brain-*` branches
- **PII-scrubbed:** No personal paths, domains, or credentials in this repo
- **Pointer memory pattern:** `MEMORY.md` keeps compact pointers (~2,200 chars), full detail lives in brain directories via gbrain
- **Privacy by default:** Memory files (`MEMORY.md`, `USER.md`) are gitignored in every brain source — never cross-contaminate instances
- **Memory scoring rubric:** Entries must score ≥7/12 (relevance 4, accuracy 4, conciseness 2, durability 2) before writing — see `memory/README.md`
| **State routing:** Information flows through a decision matrix — live context → session history → memory → docs, in that priority order — see `src/skills/software-development/state-orchestrator/`
- **Project separation:** Each project gets its own gbrain source for isolation — see `docs/knowledge-isolation-architecture.md`
- **Structured development pipeline:** Work flows through a defined chain — `requirements-elicitation` → `architecture-review` → `product-requirements` → `story-decomposition` → `change-test-loop` → code review — each stage consumes the output of the prior one, reducing rework and enforcing quality gates before code is written
- **Agent execution contract:** Non-negotiable rules — real work, verified results, no simulation.

---

## Agent Execution Contract

Every agent working in this repo must follow these non-negotiable rules:

1. **Real execution, no simulation** — run actual commands, write real files, verify with tests. Never fabricate a result.
2. **Verified deliverables** — every change must be exercised and confirmed working before reporting done. A stub, plan, or single command is not a deliverable.
3. **Fix root causes, not symptoms** — when finding a bug, check sibling call paths for the same flaw. Fix the class, not just the reported site.
4. **Touch only what the task needs** — no drive-by refactors, renames, or reformatting. Add only the imports and dependencies your code requires.
5. **Batch independent lookups** — when several reads or searches don't depend on each other, issue them together in one turn instead of one at a time.
6. **Report blockers honestly** — if a tool, install, or network call fails, say so directly and try an alternative. Never substitute fabricated output.
7. **State confidence explicitly** — when uncertain, say so and explain what you know vs what you assume. The user needs actual conviction level, not a confident-sounding guess.
8. **Keep working until done** — don't stop after writing a stub, plan, or single command. Work until you've actually exercised the code or produced the requested result.
9. **Use tools, not descriptions** — never describe what you would do without actually doing it. Every response must contain tool calls that make progress or deliver a final result.
10. **Score every change** — every code change, config change, script edit,
    or deployment must be logged to the loop-governance DB. Two paths:

    **Path A — MCP tools (for agents with MCP access):**
    - Before coding: `mcp_loop_governance_cache_search(query="task description")`
    - After change: `mcp_loop_governance_cycle_query(task_id="<task>")`
    - Provide feedback: `mcp_loop_governance_feedback_accept(cycle_id=N)`
      or `mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="...", note="...")`

    **Path B — CLI tools (for pre-commit hooks, scripts, shell):**
    `score-cycle --task <id> --cycle <N> --code-file <file> --prev-code-file <file> --pass-pct <rate>`
    `loop-feedback accept <id>` / `loop-feedback override <id> --note "..."`

    For changes with no tests, use `pass-pct 100` if verification succeeded,
    `pass-pct 0` if it failed. No exceptions — without this data the system
    cannot self-improve.

11. **Tests/TDD/scoring are always the default** — every code change assumes
    RED-GREEN-REFACTOR, loop-governance scoring, and the full discipline.
    This is not optional. Only explicit opt-out phrases bypass the loop:
    - `"don't test, do X"` / `"skip tests"` — explicitly waives TDD
    - `"only review..."` / `"read-only"` — investigation with no code change
    - `"throwaway prototype"` — explicitly marked as disposable
    - `"just check..."` / `"look at..."` — read-only, no code change
    Any ambiguous or permissive phrase (`"sure"`, `"go ahead"`, `"do it"`,
    `"sounds good"`) still triggers the full loop. Erring on the side of
    doing it is always correct. The user has explicitly stated they want
    the full governance loop on every interaction, every time.

12. **Tag discovered issues as follow-ups, don't fix them inline** — when
    you find a pre-existing bug, problem, or improvement opportunity during
    other work:
    - **Do NOT fix it right there.** Fixing derails the current slice and
      creates sprawl. The user has explicitly said this causes stress.
    - **Do document it immediately** as a specific, actionable follow-up
      task using the `todo` tool (add it to your active task list with
      status `pending`).
    - **Complete the current slice first.** Then return to the documented
      follow-ups in priority order.
    - **Never silently skip** a discovered issue. "I saw this problem but
      didn't do it" without documenting it means it's forgotten forever.
      Every discovered issue must be tracked, even if it won't be fixed
      this session.

13. **Pull before push, always** — before any `git push`, fetch and rebase:
    `git pull --rebase origin <branch>`. Pushing without pulling first
    can discard remote commits or create merge bubbles. If the remote
    has new commits, your push will be rejected anyway — pull first and
    save the round trip. Set `SKIP_PRE_PUSH=1` to bypass on a specific
    push.

---

## Loop Governance — Quick Reference

### Interface: MCP tools vs CLI

| Situation | Use | Example |
|-----------|-----|---------|
| Agent before coding | `cache_search(query)` | `mcp_loop_governance_cache_search(query="build user auth")` |
| Agent session init | `config_show()` + `cycle_stats()` | At session start, query current thresholds + recent stats |
| Agent after a cycle | `feedback_accept(id)` / `feedback_override(id, ...)` | Confirm or correct the decision |
| Agent reviewing cycles | `cycle_query(task_id="...")` | Check what was scored for a task |
| Pre-commit hook | `score-cycle --task ... --pass-pct ...` | Runs automatically on `git commit` |
| Script/CI pipeline | `score-cycle --task ... --json` | Programmatic scoring without MCP |

MCP tools require the loop-governance MCP server to be registered in
`config.yaml`. CLI tools require the symlinks created by `setup.sh`.

### Session initialization sequence

Every agent session working in this repo should start with:

1. `mcp_loop_governance_config_show()` — check current thresholds/weights
2. `mcp_loop_governance_cycle_stats(days=7)` — review recent scoring health
3. `mcp_loop_governance_cache_search(query="<current task description>")`
   — learn from past similar cycles before coding

The cache grows with each session and becomes more useful over time.
If the cache DB doesn't exist yet, the first query populates it — just
keep using it.

### Per-change scoring flow

Every change follows this pattern:

```
Before coding: cache_search(task_description) ← learn from past
[Coding work — RED-GREEN-REFACTOR or config change]
After verifying: cycle_query(task_id="story-name")  ← review the cycle
                 feedback_accept / feedback_override ← train the model
```

### Multi-file changes — how to score

When a single change touches multiple files:

| Pattern | What to do |
|---------|------------|
| One logical change across N files | Score once. Use the most representative file as `--code-file`. Describe scope in the task name. |
| Independent changes in same session | Score each logical change separately with distinct task IDs (e.g. `auth-endpoint`, `config-logging`) |
| Config changes across 2+ files | Score once. Omit `--test-file`. `pass-pct 100` if verified. |

For CLI scoring, `--code-file` should be the file that best represents
the change's purpose (typically the main implementation file, not config
or test files).

### Scoring guidelines by change type

| Change Type | `--test-file` | `--pass-pct` |
|---|---|---|
| Code change (TDD cycle) | Test file | Actual test pass rate |
| Config/IT change | N/A (omit) | 100 if verification passed, 0 if failed |
| Script edit | Any invocation that proves it works | 100 if ran without error |
| Deployment | Health check endpoint or proof of life | 100 if healthy |

The goal is not perfection — it's a record of what was changed, how it was
verified, and what the system decided. Every logged cycle trains the scoring
model. A config change scored at pass-pct 100 with no test file is far more
valuable than an unscored config change that silently breaks later.

### Troubleshooting scoring failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `embedding failed` / `Ollama connection refused` | Ollama not running | `ollama serve` or `brew services restart ollama` |
| `Model nomic-embed-text not found` | Model not pulled | `ollama pull nomic-embed-text` (274 MB) |
| `DB locked` | Concurrent score-cycle process | Wait and retry, or `rm ~/.hermes/data/loop-governance.db-journal` |
| `score-cycle not found` | Symlink missing | `bash ~/hermes-cortex/src/loop-governance/setup.sh --symlinks-only` |
| `warning: all tests failed — score may be inaccurate` | Test suite broken | Fix tests first, then re-score |
| MCP tool returns `error` | MCP server not registered | `hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback protocol:** If scoring is genuinely blocked (Ollama down, DB
corrupt, network unreachable):
1. Diagnose with `bash ~/.hermes-cortex/tools/loop-governance/verify.sh`
2. If fix takes > 2 minutes, record the change manually by running
   `score-cycle` once the issue is resolved
3. Never skip entirely — the cron auditor will flag unscored changes

### Enforcement layers

| Layer | What | How to install | Bypass |
|-------|------|---------------|--------|
| Pre-commit hook | Runs `score-cycle` on every `git commit` | `bash ~/.hermes/scripts/install-score-hook.sh --all` | `SKIP_SCORE=1` |
| SOUL.md directive | Rule appears in every Hermes session's system prompt | Edit `~/.hermes/SOUL.md` (see README) | Remove the directive |
| Cron auditor | Scans every 6h for unscored changes | Auto-created by `install-hermes-crons.sh` | N/A |

### Setup first time

```bash
# Full install — deps, symlinks, config, crons
bash ~/hermes-cortex/src/loop-governance/setup.sh

# Register the MCP server (so agents can use MCP tools)
hermes mcp add \
  --command python3 \
  --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py \
  loop-governance

# Pull the embedding model (required for scoring)
ollama pull nomic-embed-text

# Deploy pre-commit hooks across all repos
bash ~/.hermes/scripts/install-score-hook.sh --all

# Verify everything
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```

**Dependencies:** Ollama + **nomic-embed-text** (for scoring — the only
model required). 274 MB. Run `bash src/loop-governance/cleanup-ollama.sh`
to remove unnecessary models and free disk space.

---

## Skill Miner (Automated, Runs Weekly)

`skill-miner` runs every Monday 6am on each agent's machine. It scans local data for reusable patterns, scores them with nomic-embed-text, and sends top findings to Moses via the agent inbox automatically. No manual effort needed.

**What it mines (locally, PII-scrubbed):**
- Loop governance DB — high-scoring TDD cycles
- Session history — successful patterns from conversations
- Agent memory — MEMORY.md, USER.md content
- Custom skills — skills installed locally but not in the repo (full SKILL.md sent)

**Output:** Top 5 findings sent to `to=moses` (default) with `cc=luke` via the agent inbox. Moses reviews, consolidates, and pushes to hermes-cortex.

**Addressing:** Messages default to `to=moses`. Use `to=all` for broadcasts, `cc=agent` for carbon copies. Every message auto-CCs Luke.

## Autonomous Agent Reliability Patterns

Based on Karpathy's research (41% → 3% mistake rate reduction with explicit constraints):

- **Task Contract** — For 3+ step tasks, define goal/success criteria/constraints/checkpoints *before* executing. Template: `docs/templates/task-contract.md`
- **Checkpoint Verification** — Verify each step before proceeding. Fixing state retroactively is 10x harder.
- **Conflict Surfacing** — When detecting multiple patterns, surface the conflict explicitly. Do NOT blend silently.
- **Read-Before-Write** — Read a file before editing it unless creating from scratch. 90% of mistakes come from missing context.
- **Eval-Driven Development** — Define evals BEFORE building. Capability evals (new features) + regression evals (maintain ≥95%). Skill: `eval-harness`. Scripts: `run-evals.py`, `analyze-failures.py`.

---

## Structured Development Pipeline

When building new features or making significant changes, use this structured
workflow. Each stage consumes the output of the prior one, reducing rework
and enforcing quality gates before code is written:

```text
requirements-elicitation (structured requirements gathering)
    ↓
architecture-review (multi-role architecture review)
    ↓
product-requirements (concise product spec)
    ↓
story-decomposition (user-visible, testable stories)
    ↓
change-test-loop (RED-GREEN-REFACTOR with lessons)
    ↓
code-review (security scan, quality gate)
```

---

## ⚡ Daily Priority Check-in (Luke's multi-agent setup)

**Cron jobs:**
- `titus-daily-briefing` — 8:00am KST, posts to GitHub issue #1
- `daily-priority-checkin` — 8:30am KST, delivers to `origin` (Telegram)

**Purpose:** Start each day with focused alignment on the user's #1 priority, incorporating cross-agent context from Titus.

**Workflow:**

| Time | Agent | Action |
|------|-------|--------|
| 8:00am | Titus | Analyzes repos on Luke's MacBook (all except hermes-cortex). Posts briefing as comment on **GitHub issue #11** in fleet-operator/hermes-cortex |
| 8:30am | Moses | Reads latest comment from **GitHub issue #11** via `gh api`. Asks user: "What is your #1 priority for today?" |
| 8:30am+ | Moses | Breaks priority into 2-4 actionable tasks. Incorporates Titus's suggestions. Updates memory. Begins execution. |

**Why GitHub Issues:** Cross-machine bridge — Titus writes repo comments, Moses reads via `gh api`. Natural audit trail.

**Why this matters:** Prevents context-switching, builds historical record of focus areas, creates natural daily rhythm.

|---
|-------|-------|---------|
| Elicit | `requirements-elicitation` | Structured requirements gathering from user goals |
| Review | `architecture-review` | Architecture review with weighted decision matrix |
| Spec | `product-requirements` | 1-page PRD — problem, solution, constraints, open questions |
| Slice | `story-decomposition` | Break feature into independently deliverable stories |
| Build | `change-test-loop` | LEARN-RED-GREEN-REFACTOR with lesson-aware memory |
| Review | `code-review` | Pre-commit review: security, quality, auto-fix |

Load the relevant skill with `skill_view(name)` when entering each stage.

---

## Common Tasks

- **Add troubleshooting entry:** Edit `docs/troubleshooting.md`, add numbered section, update changelog
- **Add a template:** Place in `docs/templates/`, update `install.sh`
- **Modify install:** Edit `install.sh` — 26 steps, idempotent
- **Update Docker config:** Edit `deploy/docker-compose.langfuse.yml` (see docs/troubleshooting.md for env vars)
- **Upgrade gbrain:** See `docs/gbrain-v2-taxonomy.md`
- **Install scoring pre-commit hooks:** `bash ~/.hermes-cortex/scripts/install-score-hook.sh --all`
- **Add SOUL.md directive:** Edit `~/.hermes/SOUL.md` to add "Score every change" (see README)
- **Verify scoring enforcement:** `bash ~/.hermes-cortex/scripts/install-score-hook.sh --list`

## Rules

- No secrets in this repo. `.env`, `*.pem`, `*.key` are gitignored.
- Keep docs current when changing install behavior.
- MIT License — be permissive.

## ⚡ Agent Handoffs (Luke's deployment — session-to-session notes)

### ⚡ 2026-06-19 — Monitoring timestamps switched to KST (Seoul time)

**Change:** All monitoring scripts now output timestamps in KST (UTC+9) instead of UTC.

**Affected scripts:** `orch-team-health.py`, `system-alert.py`, `service-recovery.py`, `orch-team-messages.sh`

**Rationale:** User is in Seoul (KST). Timestamps should match user's local time for faster incident response.

---

### ⚡ 2026-06-19 — Cron reference

| Cron | Schedule | Type | Script/Skill | Deliver | Purpose |
|------|----------|------|--------------|---------|---------|
|| `agent-auto-remediate` | `*/5 * * * *` | LLM+skill | `auto-remediation` skill | `local` | Auto-fix cron/inbox/service issues |
| `remediation-sensor` | `*/5 * * * *` | no_agent | `remediation-sensor.py` | `local` | Companion diagnostics sensor |
| `service-recovery` | `*/5 * * * *` | no_agent | `service-recovery.py` | `origin` | Auto-restart crashed services |
| `hermes-update` | `23 22 * * *` | no_agent | `hermes-update.sh` | `origin` | Daily Hermes Agent upgrade + config migrate + doctor |
| `hermes-cortex-sync` | `33 22 * * *` | no_agent | `hermes-cortex-sync.sh` | `origin` | Daily repo pull + tool re-sync |
|| `orch-team-health` | `*/10 * * * *` | no_agent | `orch-team-health.py` | `origin` | Cross-agent health polling (orchestrator only) |
| `system-alert-watchdog` | `*/10 * * * *` | no_agent | `system-alert.py` | `origin` | Resource threshold alerts |
| `orch-team-messages` | `*/10 * * * *` | no_agent | `orch-team-messages.sh` | `origin` | Flag urgent agent messages |
| `inbox-sensor` | `*/10 * * * *` | no_agent | `inbox-sensor.py` | `local` | Detect new broadcast messages |
| `system-heartbeat` | `*/30 * * * *` | no_agent | `heartbeat.py` | `local` | System health check |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | `memory-to-brain.py` | `local` | Memory persistence to gbrain |
| `score-auditor` | `0 */6 * * *` | no_agent | `score-auditor.py` | `origin` | Scans for unscored file changes (Rule #10) |

**Troubleshooting:**

```bash
# List all crons
hermes cron list

# Recreate all crons (force)
bash ~/.hermes/scripts/install-hermes-crons.sh --force

# Dry-run to see what would change
bash ~/.hermes/scripts/install-hermes-crons.sh --dry-run

# Remove all crons
bash ~/.hermes/scripts/install-hermes-crons.sh --uninstall

# Check cron job health
cat ~/.hermes/cron/jobs.json | python3 -m json.tool
```

---

### 2026-06-15 — Auto-remediation system (general — applies to all agents)

**What:** Every Hermes agent now has an auto-remediation pipeline that catches and fixes cron job failures, resource issues, and agent inbox help requests without user intervention.

**Components (all in `src/scripts/`):**

| Script | Type | Schedule | Purpose |
|--------|------|----------|---------|
| `cron-auto-remediate.sh` | Diagnostic shell | On-demand | Structured diagnostics + fix actions (fix-missing, fix-git, fix-perms, fix-purge) |
| `system-alert.py` | no_agent watchdog | Every 10m | Resource alerts + auto-cleanup (purge at 85% mem, brew/docker prune at 90% disk) |
| `service-recovery.py` | no_agent watchdog | Every 5m | Auto-restart nginx, Ollama, gbrain, Langfuse, restore missing scripts |
|| `orch-team-messages.sh` | no_agent watchdog | Every 10m | Flags agent error messages with remediation markers |
|| `agent-auto-remediate` (skill) | LLM-driven cron | Every 5m | Orchestrator: checks errored cron jobs + inbox remediation markers, applies fixes |

**Skill location:** `src/skills/devops/auto-remediation/SKILL.md`

**Setting up on a new agent:** Each agent sets `AGENT_NAME` env var or `~/.hermes/moses-inbox.conf` so health reports identify themselves. Default: hostname.
1. `install.sh` copies all scripts to `~/.hermes/scripts/`
2. `install-hermes-crons.sh` (auto-run by install.sh) creates essential cron jobs:
   - `agent-auto-remediate` (every 5m, skill-based) — checks errors, applies fixes
   - `remediation-sensor` (every 5m, no_agent) — companion diagnostics sensor
   - `system-heartbeat` (every 30m, no_agent) — system health monitoring
   - `orch-team-health` (every 10m, no_agent) — agent health polling _(orchestrator only)_
   - `system-alert-watchdog` (every 10m, no_agent) — resource alerting
   - `service-recovery` (every 5m, no_agent) — auto-restart crashed services
   - `memory-to-brain-sync` (every 6h, no_agent) — memory persistence
   - `inbox-sensor` (every 10m, no_agent) — detect new broadcast messages
   - `orch-team-messages` (every 10m, no_agent) — flag urgent requests
3. The LLM-driven cron (`agent-auto-remediate`) loads the skill and runs the 3-phase workflow:
   - Phase 1: Check errored cron jobs
   - Phase 2: Check agent inbox remediation markers
   - Phase 3: Spot-check system resources
4. silent when healthy, brief when fixes applied, escalate after 3 failures

### ⚡ 2026-06-12 — Titus: gbrain sync-watch vs autopilot conflict

**Problem:** `src/scripts/install-gbrain-sync.sh` creates a sync-watch daemon
(`com.gbrain.sync-watch`) that runs `gbrain sync --all --skip default` every
120s. But `gbrain autopilot` (a self-maintaining daemon that handles sync
internally every ~150s) holds an exclusive PGLite 0.4.x connection. Any
second process trying to open the same `brain.pglite` crashes with:
`PGLite failed to initialize its WASM runtime — Aborted()`.

This is NOT a WASM bug — it's a single-connection lock conflict with a
misleading error message.

**Fix (commit `7f2205d` — not yet pushed):**
- `install-gbrain-sync.sh` now checks for `com.gbrain.autopilot` first and
  skips sync-watch setup if autopilot is present
- `cortex-update.sh` restarts autopilot when present; sync-watch as fallback
- `cortex-health.sh`, `heartbeat.py`, `dashboard/server.py`, `install.sh`
  verify script all check autopilot first, fall back to sync-watch
- After this fix, running `install.sh` on a system with autopilot will
  output: `gbrain autopilot detected — autopilot handles sync internally,
  skipping sync-watch`

**For existing installs that already have both daemons:**
Stop the redundant one: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.sync-watch.plist`
Disable it: `mv ~/Library/LaunchAgents/com.gbrain.sync-watch.plist{,.disabled}`
Or re-run `install.sh` and the new guard will skip re-creating it.

---

### ⚡ 2026-06-22 — Titus: Alembic migration fork prevention (all agents working on Python projects with Alembic)

**Problem:** Parallel agents creating Alembic migrations from the same parent head produce a fork (multiple heads), which causes `docker compose build` to fail at container startup.

**Three-layer defense (every project with Alembic MUST implement ALL layers):**

| Layer | Location | What it guards | Fails at |
|-------|----------|----------------|----------|
| **Pre-build check** | `./run build` runs `python3 alembic/check-heads.py` | `docker compose build` via `./run` | Build time |
| **Dockerfile gate** | `RUN python3 alembic/check-heads.py` in Docker build stage | Direct `docker compose build` (bypassing `./run`) | Docker build time |
| **Migration creation guard** | `./run migration:new` checks single head BEFORE and AFTER `alembic revision` | Parallel agents both creating from same parent head | Migration creation time |

**Setup:**

1. Create `alembic/check-heads.py` — static-analysis script that parses ALL migration files with correct type-annotation-aware regex (`(?::\s*.*?)?` for both `revision` and `down_revision`). The script auto-discovers versions via `Path(__file__).parent / "versions"`.

2. In the Dockerfile build stage (after `uv sync`):
   ```dockerfile
   COPY alembic/ alembic/
   RUN python3 alembic/check-heads.py
   ```

3. In `./run`, add `cmd_migration_new()` that wraps `alembic revision --autogenerate` with pre/post single-head verification. Register it as `migration:new` in the case dispatch.

4. In `entrypoint.sh`, pre-check head count with an explicit `HEAD_COUNT` check before `alembic upgrade head` — separate error for multi-head vs upgrade failure.

5. Add `!alembic/check-heads.py` to `.dockerignore` so the script is accessible during build.

**Regex pitfall:** The original regex `(?:\s*\w+)?` silently skipped ALL files using new-style type annotations like `revision: str = "001"` and `down_revision: tuple[str, ...] | None = (...)`. The correct regex is `(?::\s*.*?)?` — the explicit colon anchors the type annotation match.

**Skill:** `project-run-scripts` skill has been updated with all patterns, the fixed script, and template code. Load with `skill_view(name="project-run-scripts")`. The check script is at `scripts/check-alembic-heads.py` in the skill. To use the self-locating variant, place it at `alembic/check-heads.py` in the project.

**Related skills:** `change-test-loop` (use `./run migration:new` instead of bare `alembic revision` during test-driven development).

---

### 2026-06-22 — Titus: API type ↔ frontend field name sync

**Problem:** TypeScript types in `api-types.ts` diverged from the actual backend API response. `SocietyRead` had `code` + `territory_code` but the API returned `soc_code` + `territory`. This caused blank UI cells + build failures in the Docker web image.

**Root cause:** Types were hand-written, not auto-generated from the API. When the backend schema changed, the frontend types weren't updated in sync.

**Prevention (agents working on frontend/API):**

1. **When creating/updating a Pydantic schema on the backend, update the TS type simultaneously.** The TS type at `apps/web/src/lib/api-types.ts` must mirror `SocietyRead`/`SocietyCreate`/`SocietyUpdate`.

2. **After changing a TS type, search ALL references** to the old field name across the entire frontend. A single grep catches what the LSP may miss in staged/cached files:
   ```bash
   grep -rn 'oldFieldName' --include='*.ts' --include='*.tsx' apps/web/src/
   ```

3. **Run `npx tsc --noEmit`** before committing — but note this only catches errors in files the TS server has indexed. Run it AFTER saving all changes to get fresh diagnostics.

4. **Check the Docker web build** after any TS type changes — the Next.js production build (`next build`) is stricter than `tsc --noEmit` in some cases. Test with a targeted `docker compose build web` before pushing.

5. **Consistent field naming convention:**
   - Backend (Python): `snake_case` — e.g., `soc_code`, `territory`
   - Frontend (TypeScript): match the API response exactly (`soc_code`, `territory`)
   - Never alias or remap field names between the API response and TS types

---

### ⚡ 2026-06-29 — Agent inbox routing: 3-tier failover chain

**Architecture:**

| Tier | Target | Host:Port | Route | Notes |
|------|--------|-----------|-------|-------|
| 1st | Moses | `your-domain.com:13004` | Remote | Primary orchestrator inbox |
| 2nd | Esther | **`your-domain.com:23004`** | External → `127.0.0.1:13004` | Backup orchestrator inbox |
| 3rd | Local | `127.0.0.1:8903` | Local only | Filesystem inbox (same machine) |

**How Moses & Esther share the same IP:**

Both run on machines behind `your-domain.com` (IP `121.129.5.54`):
- Moses serves the inbox on port **13004**
- Esther serves the inbox on port **23004** (external) → maps to `127.0.0.1:13004` on Esther's server
- Standard web ports (80/443) serve the main site, independent of agent inboxes

**For peer agents (Titus, Gisu, Joseph, Kustos):**

Configure `~/.hermes/moses-inbox.conf` with Moses as primary and Esther as fallback:

```ini
MOSES_INBOX_URL=https://your-domain.com:13004          # 1st: Try Moses
MOSES_INBOX_FALLBACK_URL=https://your-domain.com:23004 # 2nd: Esther backup
MOSES_INBOX_AUTH=agent_name:password
AGENT_NAME=<agent-name>
```

When Moses is unreachable (connection timeout), the MCP server automatically cascades to the fallback URL.

**Moses (primary orchestrator on the server):**

Moses's inbox server runs locally on `127.0.0.1:13004`, so he connects directly:

```ini
MOSES_INBOX_URL=http://127.0.0.1:13004                       # Local inbox server
MOSES_INBOX_AUTH=moses:<redacted>
AGENT_NAME=moses
```

No fallback needed — Moses IS the primary. If his server is down, peer agents cascade to Esther.

**Exception — Esther (backup orchestrator):**

Esther's own config uses a different fallback chain since she runs the local inbox server:

```ini
MOSES_INBOX_URL=https://your-domain.com:13004          # 1st: Try Moses
MOSES_INBOX_FALLBACK_URL=http://127.0.0.1:13004             # 2nd: Local Esther server
MOSES_INBOX_THIRD_URL=http://127.0.0.1:8903                 # 3rd: Local fallback port
MOSES_INBOX_AUTH=esther:<redacted>
AGENT_NAME=esther
```

Esther doesn't route to herself via the external IP — she goes direct to localhost for lower latency and independence from external networking.

**Technical implementation:**

- `inbox-mcp.py` reads `MOSES_INBOX_URL`, `_FALLBACK_URL`, and `_THIRD_URL` from config
- `_request()` iterates through the URL chain in order. If a URL fails with a connection error (timeout, refused), it cascades to the next. HTTP 4xx/5xx responses are NOT connection errors — if the server responds, it's considered alive.
- Each URL is logged on connection attempt so debugging is transparent
- Source: `src/mcp-servers/inbox-mcp.py`

**Testing the chain:**

```bash
# Test each tier
curl -s --connect-timeout 5 https://your-domain.com:13004/health  # Moses
curl -s --connect-timeout 5 https://your-domain.com:23004/health  # Esther (ext)
curl -s http://127.0.0.1:8903/health                                    # Local
```

---

### ⚡ 2026-06-26 — Esther: backup orchestrator setup

**What:** Esther (`worker-5`, hostname `esther`) is set up as a backup orchestrator. If Moses (`moses-server`) goes down, Esther handles agent inbox messages, auto-remediation, and system health.

**Key changes to the repo:**

1. **`src/agent-registry.json` converted from array → dict format (v2).** The original v1 format had `agents` as an array of objects. But `orch-team-messages.sh` calls `data.get('agents', {}).keys()` and `generate-inbox-wrappers.py` calls `agents.items()` — both expect a **dict** keyed by agent name, not an array. The schema doc at `src/skills/devops/agent-inbox/references/agent-registry.md` already documented dict format; the sample file just didn't match. v2 adds:
   - `routing.broadcast_topics` — topics treated as broadcast channels
   - `routing.agent_prefix_topics` — when `true`, every agent name auto-becomes a broadcast topic
   - `inbox_user`, `inbox_watch_schedule`, `inbox_deliver` per agent — used by `generate-inbox-wrappers.py`

2. **`process-agent-messages` cron created** (every 10m, LLM-driven, toolsets: terminal+file+web). Companion script: `orch-moses-inbox-remediate.sh` reads remediation markers and outputs structured JSON.

3. **`orch-moses-inbox-remediate.sh`** — companion script that reads `~/.hermes/state/remediate/` markers (written by `orch-team-messages.sh`) and outputs JSON for the LLM cron to process.

4. **`orch-weekly-auto-fix.py`** — safety-net auto-fix script with built-in verification.

**Cron addition to the standard set:**

| Cron | Schedule | Type | Script/Skill | Deliver | Purpose |
|------|----------|------|--------------|---------|---------|
| `process-agent-messages` | `*/10 * * * *` | LLM | terminal+file+web | `local` | Process inbox remediation markers (backup orchestrator) |

**Setup checklist for a new backup orchestrator:**

```bash
# 1. Copy agent-registry.json to state dir
cp ~/.hermes-cortex/scripts/agent-registry.json ~/.hermes/state/agent-registry.json

# 2. Install crons
bash ~/.hermes-cortex/scripts/install-hermes-crons.sh

# 3. Copy orchestrator-specific scripts
cp ~/hermes-cortex/scripts/orch-moses-inbox-remediate.sh ~/.hermes/scripts/
cp ~/hermes-cortex/scripts/orch-weekly-auto-fix.py ~/.hermes/scripts/

# 4. Create process-agent-messages cron (replace with actual cron create cmd)
# See src/agent-registry.json for reference

# 5. Start gbrain autopilot
gbrain autopilot --repo ~/brain/default --interval 300 &

# 6. Fix score-cycle symlink (verify.sh reports warning otherwise)
ln -sf ~/.hermes-cortex/tools/loop-governance/score_cycle.py ~/.local/bin/score-cycle
```

**Expected false positives:**
- `system-heartbeat` exits code 1 with `❌ gbrain sync daemon: DOWN` on Linux — this is expected because `com.gbrain.sync-watch` is a macOS launchd service. The actual gbrain autopilot daemon runs fine.
- Loop governance `verify.sh` reports 1 warning about `score-cycle` CLI — the MCP tools work fine; the CLI symlink can be fixed with the `ln` command above.
