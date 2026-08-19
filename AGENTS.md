# Agent Guidelines — Hermes Cortex

> **⚠️ THREE HARD RULES — Every Agent Must Follow**
>
> **RULE 1: LOAD TASK-START FIRST — `skill_view('task-start')` is your first tool call on every task.** Nothing precedes it; a task not preceded by it is a trust violation. It bundles the pre-task sequence: cache_search → begin_change → always-skills (agent-flow, reasoning-patterns, reflexion-check, change-checklist, survey-before-action, cortex-preflight, agent-contract) → classify → work.
>
> **RULE 2: USE LOOP GOVERNANCE ALWAYS.** Every change: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. Write tools block without a lock. **Close out (2026-08-08):** `end_change()` refuses until scored; `begin_change()` refuses while PENDING cycles exist. Never stack PENDING. **Hook bypass blocked:** `git -c core.hooksPath=...` / `GIT_CONFIG_*=...` blocked — NOT the `--no-verify` hatch (3 tolerated, 4th+ mandated).
>
> **RULE 3: SHARE IMPROVEMENTS TO THE PUBLIC REPO.** Every improvement that benefits other agents goes into `hermes-cortex`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Core Concepts

Public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com) — Ollama, mycortex, Langfuse, Dashboard, brain dirs, sync daemon. Key dirs: `docs/`, `ops/install/`, `.hermes-cortex/`, `~/.hermes/skills/`. Principles: two-repo (public + private), PII-scrubbed, pointer memory (MEMORY.md ~2.2K → mycortex), state routing. mycortex: per-profile `mycortex_reader_<profile>` roles. See `docs/design/mycortex-multi-tenancy.md`.

## Skill loading — NOT OPTIONAL

Every session: read `.hermes-cortex/skills.yaml`, load `always` skills, classify with `agent-flow`, load `on_task` skills. See [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md).

---

## Agent Execution Contract

1. **Real execution, no simulation** — run actual commands, verify with tests.
2. **Verified deliverables** — exercised + confirmed before "done".
3. **Fix root causes, not symptoms** — check sibling call paths.
4. **Touch only what the task needs** — no drive-by refactors.
5. **Batch independent lookups** — issue together.
6. **Report blockers honestly** — never fabricate output.
7. **State confidence** — say "I don't know" when you don't.
8. **Skills-first** — `skills_list()` matching domain; load before coding.
9. **Keep working until done** — don't stop at a stub or plan.
10. **Use tools, not descriptions** — tool calls or final result in every response.
11. **Score every change** — logged to loop-governance DB; pre-commit hook auto-cycles + adversarial gate (A2/A4) on staged scripts. `--no-verify` is a logged bypass — never ship a hook-rejected change with it.
12. **Tests/TDD/scoring are the default** — opt-outs only: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **DOGFOOD EVERY CHANGE (enforced by doctor)** — a script change isn't complete until the DEPLOYED copy ran its REAL invocation: `cortex-update.sh` then `cronjob action='run'` (manual runs don't update `last_status`); prompt changes go to LIVE jobs.
14. **Tag follow-ups** — `pending` todo, finish current work, return.
15. **Pull before push** — `git pull --rebase origin <branch>`.
16. **Never print secrets** — `$(cat <file>)` subshell only; no inline `printf`/`echo`/`-u "user:pass"`.
17. **No cut corners** — every skip compounds; test deployed path, check siblings, update docs.
18. **Be thorough** — every claim tool-verified; doctor clean before done.
19. **Test before release** — suite runs 0 failures before `end_change()`; `LOW` ships blocked.
20. **Push before telling anyone to pull** — a fix on local disk is not in the repo.
21. **Identity host-derived, not env** — orchestrator = hostname (`moses`/`esther`) + home dir, never `AGENT_ID`/`AGENT_TYPE` (spoofable). Git authorship from `~/.hermes-cortex/agent.env` (per-host, gitignored); missing it blocks commit.
22. **Cross-session tasks** — `task-db.py` (see `task-persistence` skill). v2 lifecycle: `update <id> --status in_progress` before `begin_change`, `switch <target>` to change active task, `--status completed` after `end_change`. Bus commands create tasks automatically (S4) — when you process an ISSUES/PROPOSAL/IMPROVEMENTS inbox message, transition its task by correlation: `task-db.py update --by-correlation <corr> --status completed` (see `cortex-bus-automation` skill). Entry/completed task events notify Telegram.
23. **Only our repo** — `~/hermes-cortex/` ours; `~/.hermes/` not-in-repo → don't touch; `~/.hermes-cortex/state/*` + `~/.hermes/config.yaml` → live config.
24. **Sharing filter** — new/substantive only; already-in-Hermes/cortex ❌; PII-only ❌.
25. **Self-test gate** — `hc send` refuses without `--self-tested`; no bare `pass`.
26. **Skill stub guard** — cortex-update refuses to overwrite a full skill with a repo stub; doctor FAILs on stubs. Recovery: `agent-skill-stub-audit.py --send` → bus `skill-stub-recovery` → orchestrator copies → cortex-update. Never hand-fix from memory.
27. **Gateway restart for enforcer changes** — running gateway may hold the old in-memory enforcer; verify `Plugin content`; restart from a separate shell (NOT inside the gateway — blocked).
28. **State it once, then move** — after a finding/plan is established, never re-derive or re-announce it on later turns; reference it in one short clause and take the next action. Restating the same conclusion before every tool call burns tokens without progress.

---

## Pre-Ship Checklist — Every Change

Before: `survey-before-action` (search_files → map scope → skill_view). After: [`docs/reference/after-completing-work-6-questions.md`](docs/reference/after-completing-work-6-questions.md)

## Loop Governance

**Every change:** `cache_search` → `begin_change` → work → `change-checklist` → `cycle_query` → `feedback_accept/override` → `end_change` → `git push`. MCP blocks writes without lock. Pre-commit scores every commit.

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

**After-action:** Deliver what, how verified, evidence, cycle ID. See [`docs/setup-reference.md`](docs/setup-reference.md).

## Doc Freshness

| Layer | What | Who | When |
|-------|------|-----|------|
| Weekly audit | Check mandatory sections | Moses | Mon 7am KST |
| Broadcast | Notify on change | Moses | On change |
| Soul refinement | Fill gaps | Each agent | Daily 23:00 |
| Session start | Read AGENTS.md + SOUL.md | Each agent | Every session |

---

## Orchestrator-Only Domains — SUBMIT PROPOSALS, DON'T EDIT

Only orchestrators (Moses, Esther) may modify: **skills** (`skills/`), **cron scripts** (`ops/scripts/`, install crons), **governance** (`.hermes-cortex/hooks/`, pre-commit hook, enforcer plugins), **MCP servers** (`mcp-servers/`, `plugins/`), **templates** (`AGENTS.md`, `SOUL.md`, `docs/templates/`, `docs/orchestrator-only-paths.txt`), **CI/CD** (`.github/workflows/`, `VERSION`, `ops/install/`), **tests** (`tests/`, `profiles/`), **doctor** (`cortex_doctor/`).

Non-orchestrators: submit proposals via the orchestrator inbox (`📝 PROPOSAL: <what>`). The pre-commit hook blocks non-orchestrators from staging `docs/orchestrator-only-paths.txt` — the committed list IS the source of truth. Edits to shared infrastructure propagate to every agent without review.

**RULE 7b: ENFORCEMENT CHAIN — cortex-update.sh IS THE ONLY UPDATE PATH.** Enforcement files (enforcer plugin, hooks, loop-gov-mcp.py, hermes-plugin-lock) update ONLY via `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`. Direct `sudo hermes-plugin-lock unlock` is REFUSED for non-orchestrators (audit-logged); exceptions: `--cortex-update` / `--orchestrator` (moses|esther). If DOGFOOD blocks you (deployed ≠ repo enforcer): run cortex-update.sh (lock-free), re-acquire, retry. ⚠️ **Deploy ≠ load:** gateway keeps the OLD enforcer until `hermes gateway restart` (agent-blocked — ask the operator; do not loop).

**RULE 7c: BUS ACCESS — NON-ORCHESTRATORS USE THE HTTP CLIENT ONLY.** Non-orchestrators have the bus **HTTP client** (`cortex-bus.conf` + `contact-orchestrator.sh`) and NOTHING ELSE. Never install the bus server or the `cortex-bus` MCP client — the doctor WARNS on both. Role matrix: `docs/bus-architecture.md`. **Bus ACL:** per queue via `bus.permissions`; `is_admin=true` bypasses (moses). Grants in `core/cortex_bus/schema/auth.sql`.

**RULE 8: "PULL LATEST" = FULL REFRESH.** (1) `git pull origin main`, (2) `cortex-update.sh` — deploy, (3) run the doctor, (4) fix every issue until clean, (5) verify services, crons, skills.

---

## Agent Worker

Install `hermes-agent-worker` systemd `--user` service to poll inbox every 30s. See [`docs/operations-reference.md`](docs/operations-reference.md).

## Contact Protocol

See [`docs/contact-protocol-how-to-reach-orchestrator.md`](docs/contact-protocol-how-to-reach-orchestrator.md)

## Agent Cron Management

Only orchestrators (Moses, Esther) have `cronjob` MCP. Others request via `inbox_orchestrator` with subject `🔧 CRON: create|update|remove`.

Universal crons (60+): [`docs/fleet-reference.md`](docs/fleet-reference.md). **Skill Collection:** `agent-learning-collector` (6h) → `orch-skill-lifecycle` (daily 04:00).

| Subject | Location |
|---------|----------|
| Agent roles, cron rules | [`docs/agent-architecture.md`](docs/agent-architecture.md) |
| Fleet update protocol | [`docs/fleet-update-protocol.md`](docs/fleet-update-protocol.md) |
| Ollama tier, env vars, setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Plugins, scoring, workflow | [`plugins/governance-enforcer/README.md`](plugins/governance-enforcer/README.md) |
| Pipeline / Fleet / Ops refs | [`docs/pipeline-reference.md`](docs/pipeline-reference.md) · [`docs/fleet-reference.md`](docs/fleet-reference.md) · [`docs/operations-reference.md`](docs/operations-reference.md) |
| Symlink policy | [`docs/symlink-policy.md`](docs/symlink-policy.md) |

> See docs/templates/SOUL.md for canonical set. Doctor FAILS on mismatch.
