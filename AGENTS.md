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
> **RULE 7: DOCTOR OUTPUT IS DIAGNOSTIC — SUBMIT PROPOSALS TO ORCHESTRATOR**
> The doctor's `🔶 Suggestion:` lines are diagnostic hints, not instructions.
> Do NOT modify SOUL.md, AGENTS.md, or template files directly. Submit
> proposed changes to the orchestrator (Moses) via inbox message with
> subject `📝 PROPOSAL: <what>` and the change reason + content.
> Orchestrator reviews and approves.
>
> This rule exists because tool output looks like commands but is just
> diagnostic feedback. Acting on unverified tool output leads to
> unnecessary changes and template drift, which propagates to every agent.
>
> **RULE 8: "PULL LATEST" = FULL REFRESH — DO NOT CUT CORNERS**
> When the user says "pull latest", "update from repo", or any equivalent phrase, the sequence is:
> 1. `git pull origin main` — pull latest hermes-cortex
> 2. `cortex-update.sh` — update skills, crons, configs, scripts
> 3. Run doctor — check everything (`hermes doctor`, `cortex doctor`, or equivalent)
> 4. Fix every issue — do not stop until doctor reports clean
> 5. Verify — confirm all services, crons, skills are in expected state

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
  > **⚡ Pre-commit scoring hook** auto-creates a cycle on every commit. No bypass. Use `git commit --no-verify` in emergencies only.
12. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip.
14. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.
15. **Never print secrets in commands** — use `$(cat <file>)` subshell expansion. `printf`, `echo` with inline secrets, and `-u "user:pass"` are forbidden.
16. **Do not cut corners** — Every skipped step compounds. Test from deployed path, check sibling paths, update docs.
17. **Be thorough** — Verify every claim with tool output. A change isn't done until deps resolve, docs update, and doctor runs clean.
18. **Test Before Release** — Before `end_change()`, run the applicable test suite with **0 failures**. If no test suite exists, create one or acknowledge the gap. `LOW` confidence ships are blocked.
19. **Push before telling anyone to pull** — Verify the commit is on the remote. A fix on local disk is not in the repo.
20. **Set `AGENT_ID` for orchestrator identity (REQUIRED)** — Before any git commit, set `AGENT_ID=moses` (orchestrators) or `AGENT_ID=<your-name>` (non-orch). **There is no fallback** — if unset, the commit is blocked.
21. **Persistent cross-session todos** — Use `todo-db.py` for fleet-visible task tracking. See `todo-persistence` skill.
22. **Only modify files in our repo** — `~/hermes-cortex/` → ours. `~/.hermes/` (not in repo) → do NOT touch. `~/.hermes-cortex/state/*`, `~/.hermes/config.yaml` → live config.
23. **Sharing filter: only share new/substantive changes** — Already in Hermes Agent? ❌. Already in hermes-cortex? ❌. New skill? ✅. Improvement? ✅. PII-only? ❌. Test: *"Would someone running Hermes Cortex benefit?"*
24. **Self-test gate for fleet commands** — `hc send` refuses without `--self-tested`. Never use bare `pass` in except blocks.

---

## 🛡️ Orchestrator-Only Paths

Certain paths restricted to mosaic/esther. Pre-commit hook checks hostname + staged files against `docs/orchestrator-only-paths.txt` (committed version). Non-orchs: send bus message to Moses.

**How to Add:** Edit `docs/orchestrator-only-paths.txt`. The file itself is orchestrator-only + hook reads committed version (tamper-proof).

---

## Pre-Ship Checklist — Every Change

### Before starting — 3 questions
1. **Surveyed?** — `search_files()` for old name/term. `skills_list()` for category. Check git if disk finds nothing.
2. **Mapped scope?** — What scripts, docs, configs reference the change? For crons: install scripts, update.sh, doctor, schedules.
3. **Loaded skills?** — `skill_view()` on identified skills.

### After completing work — 6 questions
> See [`docs/reference/after-completing-work-6-questions.md`](docs/reference/after-completing-work-6-questions.md)

## Loop Governance
**Every change:** `cache_search` → `begin_change` → work → load `change-checklist` → `cycle_query` → `feedback_accept/override` → `end_change` → `git push`. MCP blocks writes without lock. Pre-commit scores every commit.

---

## Inbox Message Decision Framework

| Axis | Values |
|------|--------|
| **Priority** | critical | urgent | normal | notification |
| **Scope** | Simple (<3) | Moderate (3-10) | Complex (>10) | Multi-agent |

| Prio → | Simple | Moderate | Complex | Multi-agent |
|--------|--------|----------|---------|-------------|
| critical | AUTO-ACT | AUTO-ACT | AUTO-ACT + notify | Delegate + notify |
| urgent | AUTO-ACT | AUTO-ACT | AUTO-ACT + report | Delegate + report |
| normal | AUTO-ACT | AUTO-ACT | Escalate | Escalate |
| notification | Acknowledge | Acknowledge | Acknowledge | Forward |

**After-action:** Deliver what, how verified, evidence excerpt, cycle ID. See [`docs/setup-reference.md`](docs/setup-reference.md).

## Doc Freshness
| Layer | What | Who | When |
|-------|------|-----|------|
| Weekly audit | Check mandatory sections | Moses | Mon 7am KST |
| Broadcast | Notify on change | Moses | On change |
| Soul refinement | Fill gaps | Each agent | Daily 23:00 |
| Session start | Read AGENTS.md + SOUL.md | Each agent | Every session |

---

## Agent Worker
Install `hermes-agent-worker` systemd `--user` service to poll inbox every 30s. See [`docs/operations-reference.md`](docs/operations-reference.md).

---

## Contact Protocol
> See [`docs/contact-protocol-how-to-reach-moses.md`](docs/contact-protocol-how-to-reach-moses.md)

## Agent Cron Management
Only Moses has `cronjob` MCP. Others request via inbox with subject `🔧 CRON: create|update|remove`.

Universal crons (36 jobs, 7 categories): See [`docs/fleet-reference.md`](docs/fleet-reference.md). **Skill Collection:** `agent-learning-collector` (every 6h) → `orch-skill-lifecycle` (daily 04:00). See [`docs/pipeline-reference.md`](docs/pipeline-reference.md).

| Subject | Location |
|---------|----------|
| Agent roles, cron rules | [`docs/agent-architecture.md`](docs/agent-architecture.md) |
| Fleet update protocol | [`docs/fleet-update-protocol.md`](docs/fleet-update-protocol.md) |
| Ollama tier, env vars, setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Plugins, scoring, workflow | [`plugins/governance-enforcer/README.md`](plugins/governance-enforcer/README.md) |
| Pipeline Reference | [`docs/pipeline-reference.md`](docs/pipeline-reference.md) |
| Fleet Reference | [`docs/fleet-reference.md`](docs/fleet-reference.md) |
| Operations Reference | [`docs/operations-reference.md`](docs/operations-reference.md) |
| Symlink policy | [`docs/symlink-policy.md`](docs/symlink-policy.md) |

---
> See docs/templates/SOUL.md for canonical set. Doctor FAILS on mismatch.
