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
> This rule exists because every agent defaults to "create new" when "update existing" is faster, less risky, and doesn't fragment the codebase. Creating when you should have updated is the most expensive mistake — it costs review time, merge conflicts, doc drift, and future confusion. Every new file is a debt that compounds. The right fix to an existing system is almost always smaller and safer than a parallel system.
>
> **RULE 7: "PULL LATEST" = FULL REFRESH — DO NOT CUT CORNERS**
> When the user says "pull latest", "update from repo", or any equivalent phrase, the sequence is:
> 1. `git pull origin main` — pull latest hermes-cortex
> 2. `cortex-update.sh` — update skills, crons, configs, scripts
> 3. Run doctor — check everything (`hermes doctor`, `cortex doctor`, or equivalent)
> 4. Fix every issue — do not stop until doctor reports clean
> 5. Verify — confirm all services, crons, skills are in expected state
> This is not just a pull. It is a full refresh: pull → update → diagnose → fix → verify clean. No partial work. If doctor finds issues, resolve them all before reporting done.

---
## Core Concepts

**What:** Public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com) — Ollama, gbrain, Langfuse, Dashboard, brain dirs, sync daemon, utility scripts.

**Key dirs:** `docs/` (guides, templates), `ops/install/` (installer, deploy), `.hermes-cortex/` (sessions, memory, skills), skills at `~/.hermes/skills/<category>/<name>/`.

**Architecture principles:**
- **Two-repo system** — public MIT + private for secrets
- **PII-scrubbed** — no personal paths or domains
- **Pointer memory** — MEMORY.md (~2,200 chars), full detail in gbrain
- **State routing** — live context → session history → memory → docs

## Skill loading — NOT OPTIONAL

Every session: read `.hermes-cortex/skills.yaml`, call `skill_view()` for every skill in `always:` section. These define HOW you think — loaded at session start, active for every task. Then classify with `agent-flow` and load matching `on_task` skills. See [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md).

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

  > **⚡ Pre-commit scoring hook** auto-creates a cycle on every commit. No bypass — `SKIP_SCORE=1` removed. Use `git commit --no-verify` in emergencies only.

12. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip or fix inline.
14. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.
15. **Never print secrets in commands** — never pass secrets as literal strings in `terminal()` commands. Use `$(cat <file>)` subshell expansion so only the file path appears in the tool call. `printf`, `echo` with inline secret values, and `-u "user:pass"` are all forbidden patterns. <!-- Added 2026-07-13 -->
16. **Do not cut corners** — every skipped step compounds into a system failure. If a step feels optional, it is the most important one to do. Test from the deployed path, check sibling call paths, update docs, notify dependent agents. The right way is the only way.
17. **Be thorough** — verify every claim with tool output before delivering. A change is not complete until dependencies resolve, docs are updated, and the doctor runs clean. Half-done work erodes trust faster than slow work.
18. **Test Before Release** — Before calling `end_change()`, run the applicable test suite and verify **0 failures**. If no test suite exists, create one or explicitly acknowledge the gap. Ships with `LOW` confidence are blocked — fix before releasing. Test suites are not optional overhead; they are the mechanism that makes "be thorough" enforceable.
19. **Push before telling anyone to pull** — Before telling another agent "the fix is in the repo" or "pull the latest", verify the commit has been pushed to the remote (`git push origin main` completed successfully). A fix on your local disk is not in the repo. The repo is the remote. Telling agents to pull before you push wastes their time and erodes trust.
20. **'Pull latest' = full update cycle** — When the user says "pull latest", "update from repo", or similar, execute the complete sequence: `git pull`, then `cortex-update.sh`, then `cortex-doctor.py`, then fix every issue the doctor reports, then re-run doctor to confirm clean. Pulling fresh code is step one — a verified clean state is the deliverable. <!-- Added 2026-07-21 -->

21. **Persistent cross-session todos** — The `todo()` tool is per-session and ephemeral. For durable, fleet-visible task tracking, use the shared `bus.todos` table in gbrain Postgres:
  - **Session start:** `todo-db.py pending` → load DB items → `todo(todos=..., merge=true)` to restore
  - **During work:** Before `begin_change()` → `todo-db.py update <id> --status in_progress`. After `end_change()` → `todo-db.py update <id> --status completed`
  - **Session end:** `todo-db.py save-end` — archives completed items, keeps pending for next session
  - **Fleet visibility:** `todo-db.py list --agent <name>` to see any agent's tasks
  - The `todo-db.py` CLI is deployed to `~/.hermes-cortex/scripts/todo-db.py` via `cortex-update.sh`
  - See `todo-persistence` skill and SOUL.md Principle 37 for full protocol

22. **Only modify files in our repo — never touch Hermes defaults** — Hermes Agent owns everything in `~/.hermes/`. Our repo (`~/hermes-cortex/`) is the only place we create and modify files. Before editing any file:
  - If it's in `~/hermes-cortex/` → it's ours, modify freely
  - If it's ONLY in `~/.hermes/` and NOT in the repo → it's a Hermes default — do NOT touch
  - If you need to change something that only exists in `~/.hermes/`, create the source in our repo first (`~/hermes-cortex/`), then deploy via `cortex-update.sh`
  - **Exception:** Live config files (`~/.hermes-cortex/state/*`, `~/.hermes/config.yaml`) are per-machine state, not skills — modify those directly
  - **Hermes default skill examples** (do not edit): `task-start`, `session-manager`, `agent-flow`, `reasoning-patterns`, `reflexion-check`, `agent-contract`
  - **Our skill examples** (edit freely): anything with a source in `~/hermes-cortex/skills/` or `~/hermes-cortex/ops/scripts/`

23. **Sharing filter: only share new/substantive hermes-cortex changes** — When the skill lifecycle or learnings pipeline evaluates something for upstreaming (public contribution, skill sharing), apply this filter in order:
  1. **Already in Hermes Agent repo?** (default skills like `task-start`, `session-manager`, `agent-flow`) → ❌ Skip. These are the framework, not ours to share.
  2. **Already in hermes-cortex repo with no substantive change?** → ❌ Skip. Already shared with the fleet.
  3. **Newly created hermes-cortex skill?** → ✅ Share.
  4. **Substantive improvement to an existing hermes-cortex skill?** (new steps, pitfall sections, corrected commands) → ✅ Share the delta.
  5. **PII-only, ephemeral, or one-off fix?** → ❌ Keep local.

  The test: *"Would someone running Hermes Cortex benefit from this? Or is it already available to them through either the Hermes or hermes-cortex repos?"* If the answer is the latter, don't share.

24. **Self-test gate for fleet commands** — `hc send` refuses to send to fleet agents without `--self-tested` flag. This is CLI-enforced at the tool level, not a suggestion. Before dispatching any command to a fleet agent, run the self-test first and pass the flag. Additionally, never use bare `pass` in except blocks — adversarial verification flags these as bypasses. Use meaningful fallback logic or `# noqa` with justification.

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
| Plugins, tools, scoring, agent workflow, troubleshooting | [`plugins/hermes-governance-enforcer/README.md`](plugins/hermes-governance-enforcer/README.md) |
| Pipeline Reference (lessons, sessions, skills, memory, quality) | [`docs/pipeline-reference.md`](docs/pipeline-reference.md) |
| Fleet Reference (agent summary, cron jobs, auto-remediation) | [`docs/fleet-reference.md`](docs/fleet-reference.md) |
| Operations Reference (inbox architecture, offline code, rules) | [`docs/operations-reference.md`](docs/operations-reference.md) |
| Health monitoring, agent setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Symlink policy (Hermes vs Cortex layout) | [`docs/symlink-policy.md`](docs/symlink-policy.md) |

---
> Updated 2026-07-23: Added references to agent-architecture, fleet-update-protocol, PRDs, agent profiles.
> See docs/templates/SOUL.md for the canonical set. Doctor now FAILS on mismatch.
