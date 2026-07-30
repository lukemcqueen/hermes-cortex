# Agent Guidelines — Hermes Cortex

> **⚠️ THREE HARD RULES — Every Agent Must Follow**
>
> **RULE 1: LOAD TASK-START FIRST — `skill_view('task-start')` is your first tool call on every task.**
> No other tool call precedes it. This rule sits above all others. A task not preceded by `task-start` is a trust violation. The `task-start` skill loads `survey-before-action`, `agent-flow`, `reasoning-patterns`, `reflexion-check`, `change-checklist`, and `agent-contract` — all mandatory before any work begins. Also load `cortex-preflight` (devops) for repo-specific pre-flight checks.
>
> **RULE 2: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. MCP server blocks write tools without a lock.
>
> **RULE 3: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement that benefits other agents goes into `hermes-cortex`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
>
> **RULE 4: DOCUMENTATION IS NOT OPTIONAL**
> Every change includes doc updates. If another agent would be confused by the change without reading an updated doc, the doc must be updated before the governance lock is released. `docs/`, `AGENTS.md`, `SOUL.md`, and `cron-schedules.md` must reflect reality after every change.
>
> **RULE 5: CLEAN UP AFTER YOURSELF**
> If you rename a cron, update BOTH the `create_cron` call AND the uninstall array in the same commit. If you create a new cron with a new name, remove the old one. If you leave test artifacts, delete them before `end_change()`. The doctor's expected-cron list is parsed from install script uninstall arrays — drift between create and uninstall arrays breaks validation silently. Run `fix-cron-duplicates.py` before closing any cycle that touched install scripts.
>
> **RULE 6: PROVE EXISTING CAN'T HANDLE IT BEFORE CREATING NEW**
> Before creating any new script, skill, config, mechanism, or message type:
> 1. `search_files()` for existing solutions with 3+ different search terms
> 2. `skills_list()` and load matching skills **and their references**
> 3. Check if the existing system can be extended/wired instead of replaced
> 4. If the capability exists but isn't wired, **wire it** — don't rebuild it
>
> This rule exists because every agent defaults to "create new" when "update existing" is faster. Every new file is a debt that compounds.
>
> **RULE 7: "PULL LATEST" = FULL REFRESH — DO NOT CUT CORNERS**
> When the user says "pull latest", "update from repo", or any equivalent phrase, the sequence is:
> 1. `git pull origin main` — pull latest hermes-cortex
> 2. `cortex-update.sh` — update skills, crons, configs, scripts
> 3. Run doctor — check everything (`hermes doctor`, `cortex doctor`, or equivalent)
> 4. Fix every issue — do not stop until doctor reports clean
> 5. Verify — confirm all services, crons, skills are in expected state
> This is a full refresh: pull → update → diagnose → fix → verify clean.

---
## Core Concepts

**What:** Public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com) — Ollama, gbrain, Langfuse, Dashboard, brain dirs, sync daemon.

**Key dirs:** `docs/` (guides), `ops/install/` (deploy), `.hermes-cortex/` (state, memory, skills), skills at `~/.hermes/skills/<category>/<name>/`.

**Principles:** Two-repo (public MIT + private), PII-scrubbed, pointer memory (MEMORY.md ~2.2K → gbrain), state routing (context → history → memory → docs).

## Skill loading — NOT OPTIONAL

Every session: read `.hermes-cortex/skills.yaml`, load `always` skills, classify with `agent-flow`, load matching `on_task` skills. See [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md).

---

## Agent Execution Contract

1. **Real execution, no simulation** — run actual commands, write real files, verify with tests.
2. **Verified deliverables** — every change exercised and confirmed working before reporting done.
3. **Fix root causes, not symptoms** — check sibling call paths for the same flaw.
4. **Touch only what the task needs** — no drive-by refactors or reformatting.
5. **Batch independent lookups** — issue together, not one at a time.
6. **Report blockers honestly** — never substitute fabricated output.
7. **State confidence explicitly** — say "I don't know" when you don't.
8. **Skills-first** — before any task, `skills_list()` category matching domain. If skill matches, load it before writing code.
9. **Keep working until done** — don't stop after a stub or plan.
10. **Use tools, not descriptions** — every response must contain tool calls or a final result.
11. **Score every change** — every code/config/script edit logged to loop-governance DB.

For the full behavioral principles (rules 12-24+), see `SOUL.md` — the governance
principles, inbox framework, agent management, security rules, and ownership culture
are documented there. This file covers Hermes-Cortex-specific workflow, not
behavioral rules.

---

## 🛡️ Orchestrator-Only Paths

Certain paths in the repo are restricted to orchestrator agents (Moses and Esther) only.

### How It Works

The pre-commit hook checks two things before every commit:

1. **Is the agent an orchestrator?** — Checks hostname against `^(moses|esther)$`
2. **Is any staged file in a restricted path?** — Reads `docs/orchestrator-only-paths.txt` from the **committed** version (never the working copy)

If a non-orch agent tries to edit a restricted file, the commit is blocked with:

```
   ❌  docs/templates/ — orchestrator only

❌  Orchestrator-only files cannot be modified by non-orch agents.
    Current host: joseph
    Send a bus message to Moses/Esther with your change request.
```

### Tamper-Proof Design

- **Self-protecting**: `docs/orchestrator-only-paths.txt` itself is hardcoded as an orchestrator-only path — editing it won't bypass the restriction
- **Committed config wins**: The hook reads the committed version of the config file, not the working copy. A non-orch agent editing the config file to remove restrictions is still blocked
- **`git commit --no-verify` bypass**: Documented but discouraged — the pre-commit scoring hook logs bypasses

### How to Add a Path

Edit `docs/orchestrator-only-paths.txt` and add one path per line. That's it — the hook reads it dynamically.

```
# Example
docs/templates/
profiles/
AGENTS.md
```

### How to Request a Change (Non-Orch Agents)

Send a bus message to Moses with:
- Subject: `🔧 TEMPLATE: add|remove <path>`
- Body: why the path needs to be orchestrator-only (or why it no longer does)

Moses will process the request and update the config file.

### Doctor Detection

The `cortex-doctor.py --quiet` check includes:

- `✅ Skill drift` — detects when deployed skills differ from repo source
- `✅ SOUL.md template sync` — checks deployed SOUL.md follows the template
- `✅ SOUL.md reverse drift` — detects when deployed SOUL.md has template-only changes that weren't committed

---

## Pre-Ship Checklist — Every Change, Before and After

### Before starting work — 3 questions

These prevent wasted work and missed dependencies:

1. **Surveyed?** — `search_files()` for the old name/term across the entire repo. Also `skills_list()` for the relevant category — load any matching skill **and its references** before writing code or answering capability questions. A single rename can touch 10+ locations. A missing feature might already exist in a reference doc you haven't read. **If `search_files()` finds nothing on disk, check git** — the file may be committed but not deployed: `git log --oneline --all -- "**/<pattern>*"` and `git show HEAD:<path>`.
2. **Mapped scope?** — What install scripts, docs, configs, and other agents reference the thing I'm changing? For cron changes: check `install-crons.sh` create + uninstall arrays, `cortex-update.sh` register() calls, `cortex-doctor.py` parse functions, and `cron-schedules.md`.
3. **Loaded skills?** — `skill_view()` on any skill identified in step 1. Skills encode workflows that prevent mistakes.

### After completing work — 6 questions

> See [`docs/reference/after-completing-work-6-questions.md`](docs/reference/after-completing-work-6-questions.md)
## Session Todo Protocol

> See [`docs/reference/session-todo-protocol.md`](docs/reference/session-todo-protocol.md)
## Pre-Task Sequence — Mandatory Before Every Task

> Content relocated to [`docs/pre-task-sequence-mandatory-before-every-task.md`](docs/pre-task-sequence-mandatory-before-every-task.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## Loop Governance — Mandatory Agent Workflow

**Every change:**
1. **Before:** `mcp_loop_governance_cache_search(query="<what>")` then `begin_change(task_id="...")`
2. **After:** load `change-checklist` → `cycle_query` → `feedback_accept/override` → `end_change`
3. **Push:** `git add -A && git commit && git pull --rebase origin main && git push`

**Enforcement:** MCP blocks write tools without a lock. Pre-commit scores every commit. Full reference: [`docs/loop-governance-reference.md`](docs/loop-governance-reference.md)

---

## Inbox Message Decision Framework

| Axis | Values |
|------|--------|
| **Priority** | critical (immediate) | urgent (same-day) | normal (same cycle) | notification (ack) |
| **Actionability** | AUTO-ACT | DELEGATE | ESCALATE | ACKNOWLEDGE |
| **Scope** | Simple (<3 calls) | Moderate (3-10) | Complex (>10) | Multi-agent |

### Decision matrix

| Prio → | Simple | Moderate | Complex | Multi-agent |
|--------|--------|----------|---------|-------------|
| critical | AUTO-ACT | AUTO-ACT | AUTO-ACT + notify | Delegate + notify |
| urgent | AUTO-ACT | AUTO-ACT | AUTO-ACT + report | Delegate + report |
| normal | AUTO-ACT | AUTO-ACT | Escalate | Escalate |
| notification | Acknowledge | Acknowledge | Acknowledge | Forward |

**After-action:** Deliver **what** (summary), **how verified** (tool output), **evidence** (excerpt), **cycle ID** (for code changes).

### Confirmation Protocol — Required When correlation_id Present

> See [`docs/setup-reference.md`](docs/setup-reference.md)
## Doc Freshness: AGENTS.md + SOUL.md

| Layer | What | Who | Frequency |
|-------|------|-----|-----------|
| Weekly audit | Check mandatory sections | Moses | Monday 7am KST |
| Broadcast | Inbox message after changes | Moses | On change |
| Soul refinement | Fill mandatory gaps | Each agent | Daily 23:00 |
| Session start | Read AGENTS.md + own SOUL.md | Each agent | Every session |

**Mandatory sections:** SOUL.md: Identity, Mission, Behavioral Principles (Loop Gov + Inbox Framework), Communication, Scripture. AGENTS.md: Execution Contract, Loop Gov, Inbox Framework, Doc Freshness, Contact Protocol

---

## Agent Worker — Automated Inbox Processing

Install `hermes-agent-worker` systemd `--user` service to poll inbox every 30s and auto-process `workflow_step` messages via local Ollama. See [`docs/operations-reference.md`](docs/operations-reference.md) for setup, config, and fleet status.

Verify: `systemctl --user status hermes-agent-worker`

---

## Contact Protocol — How to Reach Moses

> Content relocated to [`docs/contact-protocol-how-to-reach-moses.md`](docs/contact-protocol-how-to-reach-moses.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## Agent Cron Management

Only Moses has `cronjob` MCP tool. Others request via inbox with subject `🔧 CRON: create|update|remove`. Fields: `CRON_NAME`, `CRON_SCHEDULE`, `CRON_PROMPT`/`CRON_SCRIPT`, `CRON_DELIVER`, `CRON_REASON`.

**Universal crons** (install-crons.sh — 36 jobs across 7 categories). Full details at [`docs/fleet-reference.md`](docs/fleet-reference.md):

| Category | Key crons |
|----------|-----------|
| 1. Auto-Remediation | See fleet-reference.md |
| 2. System Health | `system-alert-watchdog`, `swap-refresh`, `service-recovery`, `model-health-watchdog` |
| 3. Knowledge & Memory | `memory-to-brain-sync`, `auto-save-sessions`, `memory-pruning` |
| 4. Agent Inbox | `inbox-flag`, `agent-inbox` |
| 5. Governance | See pipeline-reference.md |
| 6. Performance Scorer | `llm-judge-scorer-weekday`, `llm-judge-scorer-weekend` |
| 7. Deployment-Specific | See fleet-reference.md |

**Skill Collection Pipeline:** Every agent runs `agent-learning-collector` (every 6h) → Moses runs `orch-skill-lifecycle` (daily 04:00) to evaluate and upstream. See [`docs/pipeline-reference.md`](docs/pipeline-reference.md).

Previously inlined content moved to:

| Subject | Location |
|---------|----------|
| Agent roles, capability matrix, cron rules | [`docs/agent-architecture.md`](docs/agent-architecture.md) |
| Fleet update protocol (bus message schema) | [`docs/fleet-update-protocol.md`](docs/fleet-update-protocol.md) |
| Enterprise PRDs: loop engineering, cheat detection | [`docs/prd/`](docs/prd/) |
| Ollama Model Tier, env vars, cron 3-tier | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Plugins, tools, scoring, agent workflow, troubleshooting | [`plugins/governance-enforcer/README.md`](plugins/governance-enforcer/README.md) |
| Pipeline Reference (lessons, sessions, skills, memory, quality) | [`docs/pipeline-reference.md`](docs/pipeline-reference.md) |
| Fleet Reference (agent summary, cron jobs, auto-remediation) | [`docs/fleet-reference.md`](docs/fleet-reference.md) |
| Operations Reference (inbox architecture, offline code, rules) | [`docs/operations-reference.md`](docs/operations-reference.md) |
| Health monitoring, agent setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Symlink policy (Hermes vs Cortex layout) | [`docs/symlink-policy.md`](docs/symlink-policy.md) |

---
> Updated 2026-07-23: Added references to agent-architecture, fleet-update-protocol, PRDs, agent profiles.
> See docs/templates/SOUL.md for the canonical set. Doctor now FAILS on mismatch.
