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
> Renaming a cron? Update BOTH the `create_cron` call and the uninstall array in the same commit — new name in, old one out. Delete test artifacts before `end_change()`. The doctor parses expected crons from install script uninstall arrays; drift breaks validation silently, so run `fix-cron-duplicates.py` before closing any cycle that touched install scripts.
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
> **RULE 7: ORCHESTRATOR-ONLY DOMAINS — SUBMIT PROPOSALS, DON'T EDIT**
> Only orchestrators (Moses, Esther) may modify:
>   • **Skills** — `skills/` directory, any skill creation or modification
>   • **Cron scripts** — `ops/scripts/` (all running scripts), crons, install crons
>   • **Governance** — `.hermes-cortex/hooks/`, pre-commit hook, enforcer plugins
>   • **MCP servers** — `mcp-servers/`, `plugins/`, any tool that runs on the fleet
>   • **Templates** — `AGENTS.md`, `SOUL.md`, `docs/templates/`, `docs/orchestrator-only-paths.txt`
>   • **CI/CD** — `.github/workflows/`, `VERSION`, `ops/install/`
>   • **Tests** — `tests/`, `profiles/`
>   • **Doctor** — `cortex_doctor/`
> Non-orchestrators: submit proposals to the orchestrator inbox via `📝 PROPOSAL: <what>`.
> The pre-commit hook blocks non-orchestrators from staging files in
> `docs/orchestrator-only-paths.txt` — the committed list IS the source of
> truth (stale doc references don't override it). Orchestrators add paths by
> editing that file (itself orchestrator-only). If something should be
> protected but isn't, message the orchestrator.
>
> This rule exists because edits to shared infrastructure propagate
> to every agent without review.
>
> **RULE 7b: ENFORCEMENT CHAIN — cortex-update.sh IS THE ONLY UPDATE PATH**
> Enforcement files (governance enforcer plugin, pre-commit/pre-push/post-commit/
> post-push hooks, loop-gov-mcp.py, hermes-plugin-lock) update ONLY via
> `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`. Direct
> `sudo hermes-plugin-lock unlock` is REFUSED for non-orchestrator accounts
> (audit-logged to /var/log/hermes-enforcement.log); exceptions: the sanctioned
> `--cortex-update` token (used by cortex-update.sh itself) and the
> `--orchestrator` token (moses|esther manual maintenance). If the DOGFOOD
> pre-commit check blocks you because the deployed enforcer differs from the
> repo: run cortex-update.sh (sanctioned lock-free), re-acquire your governance
> lock (deploys purge locks), then retry the commit. ⚠️ **Deploy ≠ load:** the
> RUNNING gateway keeps the OLD enforcer module in memory until `hermes gateway
> restart` — `hermes plugins disable/enable` only writes config.yaml (no hot
> reload) and agents cannot restart the gateway (lifecycle guard). If still
> blocked after a deploy, ask the host operator to restart the gateway; do not
> loop retrying. (Per-session skills markers survive deploys since 2026-08-01.)
>
> **RULE 7c: BUS ACCESS — NON-ORCHESTRATORS USE THE HTTP CLIENT ONLY**
> Non-orchestrators: you have the bus **HTTP client** (`cortex-bus.conf` +
> `contact-orchestrator.sh`) and NOTHING ELSE. Never install the bus server
> (Postgres/FastAPI/nginx) or the `cortex-bus` MCP client in `config.yaml` —
> the doctor WARNS on both. Role matrix: `docs/bus-architecture.md`.
>
> **RULE 8: "PULL LATEST" = FULL REFRESH — DO NOT CUT CORNERS**
> "pull latest" / "update from repo" means the full cycle:
> 1. `git pull origin main` — pull latest hermes-cortex
> 2. `cortex-update.sh` — deploy skills, crons, configs, scripts
> 3. Run the doctor (`hermes doctor` / `cortex doctor`) — check everything
> 4. Fix every issue — do not stop until the doctor reports clean
> 5. Verify — confirm services, crons, and skills are in expected state

---
## Core Concepts

**What:** Public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com) — Ollama, mycortex, Langfuse, Dashboard, brain dirs, sync daemon.

**Key dirs:** `docs/` (guides), `ops/install/` (deploy), `.hermes-cortex/` (state, memory, skills), skills at `~/.hermes/skills/<category>/<name>/`.

**Principles:** Two-repo (public MIT + private), PII-scrubbed, pointer memory (MEMORY.md ~2.2K → mycortex), state routing (context → history → memory → docs).

**mycortex multi-tenancy (2026-08-06):** each PROFILE connects to the brain as its own `mycortex_reader_<profile>` role — RLS keys on `CURRENT_USER`, so tenant isolation is automatic. Your host's deploy creates the role and auto-migrates legacy grants; NEVER grant personal sources to the shared `mycortex_reader`. Profile resolution: `HERMES_PROFILE` → `AGENT_NAME` → hostname (never an alphabetical `~/.hermes/profiles/*/` scan). See `docs/design/mycortex-multi-tenancy.md`.

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
  > **⚡ Pre-commit scoring hook** auto-creates a cycle on every commit. No bypass. The hook also runs the mandatory adversarial gate (A2/A4) on every staged script — `--no-verify` is a logged, audited bypass and must never be used to ship a hook-rejected change. **Bounded escape hatch:** 3 consecutive `--no-verify` commits are tolerated; the 4th+ is MANDATED — push blocked + enforcer refuses until a verified commit resets the counter. The nginx-threat-pipeline no longer uses `--no-verify` — fresh marker + blocklist allowlist sanction its commits; safety gates still run.
12. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **DOGFOOD EVERY CHANGE BEFORE DONE (enforced by doctor).** A script change isn't complete until the DEPLOYED copy ran its REAL invocation — for crons: `bash cortex-update.sh`, then `cronjob action='run' job_id=<id>` (manual `python3 script.py` doesn't update the scheduler's `last_status`). The `Script run evidence` check WARNs on any ops/scripts change in the last 7 days whose cron hasn't run since — resolve it before `end_change()`. Prompt changes go to LIVE jobs too (`cronjob action='update'`); `Cron prompt stale refs` catches missed ones.
14. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip.
15. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.
16. **Never print secrets in commands** — use `$(cat <file>)` subshell expansion. `printf`, `echo` with inline secrets, and `-u "user:pass"` are forbidden.
17. **Do not cut corners** — Every skipped step compounds. Test from deployed path, check sibling paths, update docs.
18. **Be thorough** — Verify every claim with tool output. A change isn't done until deps resolve, docs update, and doctor runs clean.
19. **Test Before Release** — Before `end_change()`, run the applicable test suite with **0 failures**. If no test suite exists, create one or acknowledge the gap. `LOW` confidence ships are blocked.
20. **Push before telling anyone to pull** — Verify the commit is on the remote. A fix on local disk is not in the repo.
21. **Agent identity is host-derived, not env** — Orchestrator status comes from hostname (`moses`/`esther`) AND the matching home dir (`/home/moses`, `/home/esther`) — never from `AGENT_ID`/`AGENT_TYPE` env vars (spoofable, grant no privileges). Git authorship comes from `~/.hermes-cortex/agent.env` (`AGENT_NAME=<your-agent>`), written per-host by `cortex-update.sh` and gitignored — the hostname→agent mapping must NEVER be committed to this public repo. Missing `agent.env` blocks the commit with setup instructions. `AGENT_ID` is obsolete — do not set it.
22. **Persistent cross-session todos** — Use `todo-db.py` for fleet-visible task tracking. See `todo-persistence` skill.
23. **Only modify files in our repo** — `~/hermes-cortex/` → ours. `~/.hermes/` (not in repo) → do NOT touch. `~/.hermes-cortex/state/*`, `~/.hermes/config.yaml` → live config.
24. **Sharing filter: only share new/substantive changes** — Already in Hermes Agent? ❌. Already in hermes-cortex? ❌. New skill? ✅. Improvement? ✅. PII-only? ❌. Test: *"Would someone running Hermes Cortex benefit?"*
25. **Self-test gate for fleet commands** — `hc send` refuses without `--self-tested`. Never use bare `pass` in except blocks.
26. **Skill stub guard + recovery** — `cortex-update.sh` refuses to overwrite a FULL deployed skill with a truncated repo stub (`is_skill_stub`: <1500 bytes AND `Full content (truncated)` or `--- End skill ---`); the doctor FAILs on repo stubs. Recovery: `agent-skill-stub-audit.py --send` on the source agent (Joseph/luke-server) → bus `skill-stub-recovery` payloads → `agent-message-handler` stages them → orchestrator copies full content over `skills/` → `cortex-update.sh`. Never hand-fix stub content from memory — re-collect from the source agent so recovery is verifiable.
27. **Restart the gateway for enforcer changes** — after `cortex-update.sh` deploys a newer governance enforcer plugin, the running gateway may still execute the old in-memory copy. Verify with the doctor's `Plugin content` check; if it shows deployed ≠ repo while the repo is current, run `hermes gateway restart` from a separate shell (NOT from inside the gateway process — blocked by the enforcer).

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
> See [`docs/contact-protocol-how-to-reach-orchestrator.md`](docs/contact-protocol-how-to-reach-orchestrator.md)

## Agent Cron Management
Only orchestrators (Moses, Esther) have `cronjob` MCP. Others request via the orchestrator inbox (`inbox_orchestrator`) with subject `🔧 CRON: create|update|remove`.

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
