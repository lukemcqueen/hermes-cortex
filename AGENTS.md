# Agent Guidelines — Hermes Cortex

This file is read by many agent tools (Claude Code, Copilot, Codex, Hermes, etc.)
on session start. It orients any agent working on this repo.

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
| `deploy/docker-compose.langfuse.yml` | Langfuse v3 with ClickHouse, MinIO, Redis |
| `.hermes-cortex/sessions/current.md` | Active session state — branch, commits, task context |
| `.hermes-cortex/sessions/archive/` | Timestamped session snapshots |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `.hermes-cortex/memory/` | Per-user agent memory (gitignored — each dev has their own) |
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
- **Structured development pipeline:** Work flows through a defined chain — `hc-elicit` → `hc-party` → `prd-lite` → `story-slicing` → `change-test-loop` → code review — each stage consumes the output of the prior one, reducing rework and enforcing quality gates before code is written
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
7. **Keep working until done** — don't stop after writing a stub, plan, or single command. Work until you've actually exercised the code or produced the requested result.
8. **Use tools, not descriptions** — never describe what you would do without actually doing it. Every response must contain tool calls that make progress or deliver a final result.

---

## Autonomous Agent Reliability Patterns

Based on Karpathy's research showing **41% → 3% mistake rate reduction** with explicit constraints, Hermes Cortex implements these reliability patterns:

### Task Contract (Pre-Execution Specification)

**For tasks with 3+ steps, define a task contract BEFORE execution.**

```markdown
## Task Contract

**Goal:** [Single sentence]

**Success Criteria:**
- [ ] [Verifiable outcome 1]
- [ ] [Verifiable outcome 2]

**Constraints:**
- Files I may touch: `[list]`
- Files I must NOT touch: `[list]`

**Checkpoints:**
1. [ ] After step X, verify Y
2. [ ] Before proceeding, confirm Z
```

**Template:** `docs/templates/task-contract.md`

### Checkpoint Verification

**Verify each checkpoint before proceeding to the next step.**

Agents often complete steps 5-6 on top of a broken state from step 4. Checkpoint verification catches failures early.

### Conflict Surfacing

**When detecting multiple patterns in the codebase, surface the conflict — do NOT blend silently.**

Silent pattern blending is how errors get swallowed twice. Surface conflicts explicitly with examples and await pattern choice.

### Read-Before-Write

**Read a file before editing it, unless creating from scratch.**

90% of Claude's mistakes come from missing context, not weak models. Reading before writing ensures the agent operates on actual state.

### Eval-Driven Development

**Define evals BEFORE building. Run capability and regression suites systematically.**

- **Capability evals:** Measure what the agent CAN do (new features)
- **Regression evals:** Ensure agent MAINTAINS learned tasks (should stay ≥95%)
- **Holdout gating:** Survivors must pass on unseen data before deployment

**Skill:** `eval-harness`  
**Scripts:** `run-evals.py`, `analyze-failures.py`  
**Weekly analysis:** `analyze-failures.py --week last` (Monday 7am cron)

---

## Structured Development Pipeline

When building new features or making significant changes, use this structured
workflow. Each stage consumes the output of the prior one, reducing rework
and enforcing quality gates before code is written:

```
hc-elicit (requirements elicitation)
    ↓
hc-party (multi-role architecture review)
    ↓
prd-lite (concise product spec)
    ↓
story-slicing (user-visible, testable stories)
    ↓
change-test-loop (RED-GREEN-REFACTOR with lessons)
    ↓
code review (security scan, quality gate
```

---

## Daily Priority Check-in

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

**Why GitHub Issues:**
- Every agent is on a separate physical machine (no shared filesystem)
- Titus has write access to hermes-cortex repo (can post issue comments)
- Moses has read access via GitHub CLI token (can read comments)
- Natural TITUS-ONLY enforcement (only Titus can write)
- Audit trail in GitHub (visible to humans)
- Works cross-machine immediately (no migration needed)

**Why this matters:**
- Prevents context-switching and reactive work
- Ensures we're always working on what matters most
- Leverages Titus's repo-specific insights (pending PRs, blockers, recent changes)
- Builds a historical record of focus areas (via memory)
- Creates natural daily rhythm for deep work

---
|-------|-------|---------|
| Elicit | `hc-elicit` | Structured requirements gathering from user goals |
| Review | `hc-party` | Architecture review with weighted decision matrix |
| Spec | `prd-lite` | 1-page PRD — problem, solution, constraints, open questions |
| Slice | `story-slicing` | Break feature into independently deliverable stories |
| Build | `change-test-loop` | LEARN-RED-GREEN-REFACTOR with lesson-aware memory |
| Review | `requesting-code-review` | Pre-commit review: security, quality, auto-fix |

Load the relevant skill with `skill_view(name)` when entering each stage. Skills live in `~/.hermes/skills/software-development/<name>/SKILL.md`.

---

## Common Tasks

|- **Add a troubleshooting entry:** Edit `docs/troubleshooting.md`, add new numbered section, update changelog
|- **Add a template:** Place in `docs/templates/`, update `install.sh` step 9 to copy it during install
|- **Modify install:** Edit `install.sh` — 26 steps, idempotent, safe to re-run
|- **Update Docker config:** Edit `deploy/docker-compose.langfuse.yml` — Langfuse v3 requires specific env vars (see docs/troubleshooting.md)
|- **Upgrade gbrain to v2 taxonomy:** See `docs/gbrain-v2-taxonomy.md` for the 15 canonical types and upgrade instructions for existing brains

## Rules

- No secrets in this repo — ever
- `.env`, `.env.*`, `*.pem`, `*.key` are gitignored
- Keep docs current when changing install behavior
- MIT License — be permissive with what's shared

## Agent Handoffs

### 2026-06-19 — Monitoring timestamps switched to KST (Seoul time)

**Change:** All monitoring scripts now output timestamps in KST (UTC+9) instead of UTC.

**Affected scripts:**
- `agent-health-monitor.py` — Health alerts
- `system-alert.py` — Resource threshold alerts  
- `service-recovery.py` — Service restart reports
- `check-agent-messages.sh` — Inbox message notifications

**Output format:** `[2026-06-19 08:48 KST]`

**Rationale:** User is in Seoul (KST). Timestamps should match user's local time for faster incident response.

---

### 2026-06-19 — Cron installation hardened

**Improvements to `install-hermes-crons.sh`:**

| Feature | Description |
|---------|-------------|
| `--force` flag | Recreate all crons (overwrites existing) |
| Script verification | Checks scripts exist before creating crons |
| Failure tracking | Exits with error if any cron creation fails |
| Better error messages | Shows which scripts are missing |

**Install script (`install.sh`) improvements:**
- Verifies Hermes Agent is installed before attempting cron creation
- Skips cron step with clear warning if Hermes not found
- Provides explicit command to run crons manually after Hermes install

**Cron job reference:**

| Cron | Schedule | Type | Script/Skill | Deliver | Purpose |
|------|----------|------|--------------|---------|---------|
| `cron-auto-remediate` | `*/5 * * * *` | LLM+skill | `auto-remediation` skill | `local` | Auto-fix cron/inbox/service issues |
| `remediation-sensor` | `*/5 * * * *` | no_agent | `remediation-sensor.py` | `local` | Companion diagnostics sensor |
| `service-recovery` | `*/5 * * * *` | no_agent | `service-recovery.py` | `origin` | Auto-restart crashed services |
| `agent-health-monitor` | `*/10 * * * *` | no_agent | `agent-health-monitor.py` | `origin` | Cross-agent health polling |
| `system-alert-watchdog` | `*/10 * * * *` | no_agent | `system-alert.py` | `origin` | Resource threshold alerts |
| `check-agent-messages` | `*/10 * * * *` | no_agent | `check-agent-messages.sh` | `origin` | Flag urgent agent messages |
| `inbox-sensor` | `*/10 * * * *` | no_agent | `inbox-sensor.py` | `local` | Detect new broadcast messages |
| `system-heartbeat` | `*/30 * * * *` | no_agent | `heartbeat.py` | `local` | System health check |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | `memory-to-brain.py` | `local` | Memory persistence to gbrain |

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

### 2026-06-15 — Auto-remediation system (all agents)

**What:** Every Hermes agent now has an auto-remediation pipeline that catches and fixes cron job failures, resource issues, and agent inbox help requests without user intervention.

**Components (all in `src/scripts/`):**

| Script | Type | Schedule | Purpose |
|--------|------|----------|---------|
| `cron-auto-remediate.sh` | Diagnostic shell | On-demand | Structured diagnostics + fix actions (fix-missing, fix-git, fix-perms, fix-purge) |
| `system-alert.py` | no_agent watchdog | Every 10m | Resource alerts + auto-cleanup (purge at 85% mem, brew/docker prune at 90% disk) |
| `service-recovery.py` | no_agent watchdog | Every 5m | Auto-restart nginx, Ollama, gbrain, Langfuse, restore missing scripts |
| `check-agent-messages.sh` | no_agent watchdog | Every 10m | Flags agent error messages with remediation markers |
| `cron-auto-remediate` (skill) | LLM-driven cron | Every 5m | Orchestrator: checks errored cron jobs + inbox remediation markers, applies fixes |

**Skill location:** `src/skills/devops/auto-remediation/SKILL.md`

**Setting up on a new agent:**
1. `install.sh` copies all scripts to `~/.hermes/scripts/`
2. `install-hermes-crons.sh` (auto-run by install.sh) creates essential cron jobs:
   - `cron-auto-remediate` (every 5m, skill-based) — checks errors, applies fixes
   - `remediation-sensor` (every 5m, no_agent) — companion diagnostics sensor
   - `system-heartbeat` (every 30m, no_agent) — system health monitoring
   - `agent-health-monitor` (every 10m, no_agent) — agent health polling
   - `system-alert-watchdog` (every 10m, no_agent) — resource alerting
   - `service-recovery` (every 5m, no_agent) — auto-restart crashed services
   - `memory-to-brain-sync` (every 6h, no_agent) — memory persistence
   - `inbox-sensor` (every 10m, no_agent) — detect new broadcast messages
   - `check-agent-messages` (every 10m, no_agent) — flag urgent requests
3. The LLM-driven cron (`cron-auto-remediate`) loads the skill and runs the 3-phase workflow:
   - Phase 1: Check errored cron jobs
   - Phase 2: Check agent inbox remediation markers
   - Phase 3: Spot-check system resources
4. silent when healthy, brief when fixes applied, escalate after 3 failures

### 2026-06-12 — Titus: gbrain sync-watch vs autopilot conflict

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
