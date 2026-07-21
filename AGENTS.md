# Agent Guidelines — Hermes Cortex

> **⚠️ FOUR HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. MCP server blocks write tools without a lock.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement that benefits other agents goes into `hermes-cortex`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
>
> **RULE 3: DOCUMENTATION IS NOT OPTIONAL**
> Every change includes doc updates. If another agent would be confused by the change without reading an updated doc, the doc must be updated before the governance lock is released. `docs/`, `AGENTS.md`, `SOUL.md`, and `cron-schedules.md` must reflect reality after every change.
>
> **RULE 4: CLEAN UP AFTER YOURSELF**
> If you rename a cron, update BOTH the `create_cron` call AND the uninstall array in the same commit. If you create a new cron with a new name, remove the old one. If you leave test artifacts, delete them before `end_change()`. The doctor's expected-cron list is parsed from install script uninstall arrays — drift between create and uninstall arrays breaks validation silently. Run `fix-cron-duplicates.py` before closing any cycle that touched install scripts.

---

## Core Concepts

**What this repo is:** A public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com). Gets you Ollama, gbrain (Postgres + pgvector), Langfuse, Cortex Dashboard, brain dirs, gbrain sync daemon, utility scripts.

### Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Guides, templates, reference docs |
| `docs/service-layer-decision.md` | **Architecture decision: user-level only for agent services** |
| `docs/linux-service-layer.md` | Linux systemd `--user` service layer guide |
| `docs/macos-service-layer.md` | macOS LaunchAgent service layer guide |
| `docs/skills-manifest-reference.md` | Skills manifest — how to manage project-level skills |
| `ops/install/install.sh` | Single-command installer |
| `ops/install/deploy/` | Langfuse + ClickHouse docker-compose |
| `.hermes-cortex/` | Agent infra: sessions, memory, skills.yaml |

## Skill loading

**Every session start:** read `.hermes-cortex/skills.yaml` and load all `always`
skills via `skill_view(name)`. Before each task, classify with `agent-flow`,
then load `on_task` skills matching the classification.

Skills live in a single global location (`~/.hermes/skills/`) — no drift, no
stale copies across repos. To add a fleet-wide skill, upstream it to
`hermes-cortex/skills/<category>/<name>/SKILL.md`.

Documentation: [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md)

### Project Directory Convention

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

### Architecture Principles

- **Two-repo system:** Public MIT repo + private repo for secrets
- **PII-scrubbed:** No personal paths, domains, or credentials in this repo
- **Pointer memory pattern:** MEMORY.md keeps compact pointers (~2,200 chars), full detail in gbrain
- **State routing:** Live context → session history → memory → docs

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

---

## Pre-Ship Checklist — Every Change, Before and After

### Before starting work — 3 questions

These prevent wasted work and missed dependencies:

1. **Surveyed?** — `search_files()` for the old name/term across the entire repo. Also `skills_list()` for the relevant category — load any matching skill **and its references** before writing code or answering capability questions. A single rename can touch 10+ locations. A missing feature might already exist in a reference doc you haven't read.
2. **Mapped scope?** — What install scripts, docs, configs, and other agents reference the thing I'm changing? For cron changes: check `install-crons.sh` create + uninstall arrays, `cortex-update.sh` register() calls, `cortex-doctor.py` parse functions, and `cron-schedules.md`.
3. **Loaded skills?** — `skill_view()` on any skill identified in step 1. Skills encode workflows that prevent mistakes.

### After completing work — 6 questions

These catch incomplete changes before they ship. Every NO means the change is not done:

1. **Arrays synced?** — If I touched cron install scripts: does every `create_cron` name have a matching entry in the same file's uninstall array? Run `fix-cron-duplicates.py` to verify.
2. **Old thing removed?** — If I created a replacement (new cron name, new script, new config), did I delete the old one? Crons don't self-destruct. Stale scripts in deploy dirs don't self-delete.
3. **Docs updated?** — Every doc that references the changed thing. At minimum: `cron-schedules.md`, `fleet-reference.md`, `AGENTS.md`, and any skill SKILL.md that mentions the old name.
4. **Syntax valid?** — Ran `bash -n` on every `.sh` I changed, `python3 -m py_compile` on every `.py`. Install scripts with broken arrays silently fail.
5. **Doctor clean?** — `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet` shows 0 failures. Don't close the governance cycle until it does.
6. **Pushed and deployed?** — `git push origin main` succeeded. Runtime copies deployed: AGENTS.md → `~/.hermes/AGENTS.md`, scripts → `~/.hermes-cortex/scripts/`.

> **If any post-work answer is NO, the change is not complete.** Do not call `end_change()` until all 6 pass. This is not optional — it's Rule 3 (documentation) and Rule 4 (cleanup) in practice.

---

## Pre-Task Sequence — Mandatory Before Every Task

This is NOT optional. Every task starts with this exact sequence,
regardless of task size, urgency, or domain.

**Start here:** Load the `task-start` skill. It prescribes the complete
11-step sequence. No other tool call comes before it.

```
skill_view(name="task-start")
```

The full sequence (also documented in `task-start`):

### Step 1: Load Always Skills

Read `.hermes-cortex/skills.yaml` (or `skills.yaml` in the project root).
Call `skill_view(name)` for every skill in the `always` section.

These skills define HOW you think and work — they are active context
for the entire task, not one-time loads.

### Step 2: Select Reasoning Pattern

Load `reasoning-patterns` (already loaded from Step 1) and choose:

| Pattern | When |
|---------|------|
| **Plan-Execute-Verify** | Default — write plan, execute steps, verify each |
| **ReAct** | Debugging, exploration — reason, act, observe |
| **Reflexion** | Add to any pattern when quality is critical |
| **Tree of Thoughts** | Design decisions with trade-offs |

**State your choice:** *"Using Plan-Execute-Verify with Reflexion check."*

### Step 3: Classify with Agent-Flow

Load `agent-flow` (already loaded from Step 1). Match the request against
the 12 workflow patterns. This determines toolset, output format, and
checklist.

### Step 4: Load On-Task Skills

After classification, read `.hermes-cortex/skills.yaml` again and call
`skill_view(name)` for every skill in the `on_task` section matching
your classification. Also call `skills_list()` for the relevant category
to discover skills not in the manifest.

### Step 5: Call Survey-Before-Action

Call `skill_view(name="survey-before-action")` and run its checklist BEFORE
creating any file, writing any code, or running any command. Search for
existing resources first.

### Step 6: Work

Execute the task using the loaded skills, following the chosen reasoning
pattern and the classified workflow pattern's checklist.

### Step 7: Reflexion Check Before Delivery

After completing the work but BEFORE presenting results:
1. Load `reflexion-check` and run the five-question audit
2. Score confidence (HIGH / MEDIUM / LOW / ZERO)
3. If LOW or ZERO: fix before delivering

### Step 8: Change Checklist Before End Change

For code/config/cron changes: load `change-checklist` and run all phases
before calling end_change(). Phase 6 (Reflexion) is mandatory.

---

## Loop Governance — Mandatory Agent Workflow

**Every change requires this sequence:**

### Before work
```python
mcp_loop_governance_cache_search(query="<what you are about to do>")
```

### After each logical change — before closing the cycle
```python
# 1. Load the change-checklist skill (mandatory before end_change)
skill_view(name="change-checklist")

# 2. Verify all 5 phases: test, multi-OS, multi-role, docs, final
# Run actual scripts. Diff outputs. Run doctor --quiet.

# 3. Score the governance cycle
mcp_loop_governance_cycle_query(task_id="<descriptive-name>")
mcp_loop_governance_feedback_accept(cycle_id=N, note="verified: <how>")
# OR if wrong:
mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="MOVE_ON", note="...")

# 4. Push changes so all agents benefit
git add -A && git commit -m "<descriptive message>"
git pull --rebase origin main && git push origin main
```

**Enforcement:** MCP server blocks write tools without a lock. Pre-commit hook runs `score-cycle` on every commit. Cron auditor flags low cycle counts.

Full reference: [`docs/loop-governance-reference.md`](docs/loop-governance-reference.md)

---

## Inbox Message Decision Framework

Three axes when processing inbox messages:

**Priority:** `critical` (immediate action) | `urgent` (same-day) | `normal` (same cycle) | `notification` (acknowledge)

**Actionability:** AUTO-ACT (I have tools) → DELEGATE (needs another agent) → ESCALATE (needs human) → ACKNOWLEDGE (FYI)

**Scope:** Simple (<3 calls, do now) | Moderate (3-10, report) | Complex (>10, escalate) | Multi-agent (delegate)

### Decision matrix

| Prio → | Simple | Moderate | Complex | Multi-agent |
|--------|--------|----------|---------|-------------|
| critical | AUTO-ACT | AUTO-ACT | AUTO-ACT + notify | Delegate + notify |
| urgent | AUTO-ACT | AUTO-ACT | AUTO-ACT + report | Delegate + report |
| normal | AUTO-ACT | AUTO-ACT | Escalate | Escalate |
| notification | Acknowledge | Acknowledge | Acknowledge | Forward |

**After-action:** Deliver **what** (summary), **how verified** (tool output), **evidence** (excerpt), **cycle ID** (for code changes).

### Confirmation Protocol — Required When correlation_id Present

> Content relocated to [`docs/setup-reference.md`](docs/setup-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

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

Each agent can install an `agent-worker` systemd `--user` service that polls their inbox every 30s and auto-processes `workflow_step` messages via local Ollama. No Hermes cron, no Moses dependency.

### Installation (one-time per agent)

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Config

> Content relocated to [`docs/reference/config.md`](docs/reference/config.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

### How it works

1. Polls `inbox_<agent>` every 30s via `curl`
2. Finds messages with `type: workflow_step`
3. If `human_review: true` → writes flag file to `~/.hermes/state/worker-pending/`, archives message (agent handles in-session)
4. Else → sends prompt to local Ollama (`qwen2.5-coder:3b`), posts result to `workflow_step_result`
5. Idempotent: tracks completed step IDs locally to prevent double-processing on restart
6. On failure (3 retries) → writes error flag file, archives message

### Verify it's working

```bash
systemctl --user status hermes-agent-worker
tail -f ~/.hermes/logs/agent-worker-<AGENT_NAME>.log
```

### Fleet status (current)

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

---

## Contact Protocol — How to Reach Moses

Any agent can send a message to Moses. Choose the right channel:

### In-session (MCP) — preferred when you have tools

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Headless (bus curl) — from workers, scripts, crons

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Message format

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Bus watchdogs (Moses only, delivered to Telegram)

Two no_agent crons provide fleet visibility:

| Watchdog | Schedule | Output | Silent when |
|----------|----------|--------|-------------|
| `bus-audit-watchdog` | `*/1 * * * *` | New message events to Telegram (`sender → recipient action @KST`) | No new messages |
| `orch-fleet-watchdog` | `*/5 * * * *` | Dashboard: agent health, active workflows with step progress, stalled step alerts | No active workflows + no issues |

- `bus-audit-watchdog` — every send event: `esther → moses send @18:06:39 KST`, `system → joseph workflow_step(review) @18:08:28 KST`
- `orch-fleet-watchdog` — every 5 min if busy: shows ✅ active / ⚠️ idle / 🌙 offline per agent, workflow chain with ✅▶⏳ per step, stalled step detection (>5 min running)

---

## Agent Cron Management

Only Moses has `cronjob` MCP tool. Others request via inbox with subject `🔧 CRON: create|update|remove`. Fields: `CRON_NAME`, `CRON_SCHEDULE`, `CRON_PROMPT`/`CRON_SCRIPT`, `CRON_DELIVER`, `CRON_REASON`.

**Universal crons** (installed by `install-crons.sh` on every agent — 36 jobs across 7 categories):

### 1. Auto-Remediation Pipeline

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### 2. System Health Monitoring
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `system-alert-watchdog` | no_agent | `*/30 * * * *` | `system-alert-watchdog.py` | origin |
| `swap-refresh` | no_agent | `0 5 * * *` | `swap-refresh.py` | origin |
| `service-recovery` | no_agent | `*/5 * * * *` | `service-recovery.py` | origin |
| `model-health-watchdog` | no_agent | `0 7 * * *` | `model-health-watchdog.py` | origin |

### 3. Knowledge & Memory
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `memory-to-brain-sync` | no_agent | `0 */6 * * *` | `memory-to-brain-sync.py` | local |
| `auto-save-sessions` | no_agent | `every 360m` | `auto-save-sessions.py` | local |
| `memory-pruning` | LLM+prompt | `0 4 * * 1` | (consolidation prompt) | origin |
| *(replaced: `harvest-lessons` → `orch-skill-lifecycle`)* | | | | |

### 4. Agent Inbox Processing
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `inbox-depth-watchdog` | no_agent | `*/1 * * * *` | `inbox-depth-watchdog.sh` | local |
| `inbox-sensor` | no_agent | `*/10 * * * *` | `inbox-sensor.py` | local |
| `inbox-flag` | no_agent | `*/10 * * * *` | `inbox-flag.py` | local |
| `agent-inbox` | LLM | `*/2 * * * *` | (inbox decision prompt + depth watchdog context) | origin |

### 5. Governance & Quality

> Content relocated to [`docs/pipeline-reference.md`](docs/pipeline-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### 6. Performance Scorer
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `llm-judge-scorer-weekday` | no_agent | `0 12,20 * * 1-5` | `llm-judge-scorer.py` | local |
| `llm-judge-scorer-weekend` | no_agent | `0 22 * * 0,6` | `llm-judge-scorer.py` | local |

### 7. Deployment-Specific

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Skill Collection Pipeline

The full skill lifecycle runs across all agents via the unified daily pipeline:

1. **Collect** — Every agent runs `agent-learning-collector` (no_agent, every 6h). First, mines recent sessions via `session-mine` to extract new lessons. Then collects skills delta, lessons delta, and session stats. Sends "Learning Report" to `inbox_moses`. Silent when nothing new (watchdog pattern).
2. **Evaluate + Upstream** — Moses runs `orch-skill-lifecycle` (LLM-driven, daily 04:00). Reads all agent reports from the bus, cross-references across agents, evaluates for consolidation/upstream candidates, patches skills, and pushes to the repo.

See [`docs/pipeline-reference.md`](docs/pipeline-reference.md) for the detailed pipeline architecture.

---

## Luke's Deployment: Profile Structure

### Active Profiles

This deployment uses the `hermes-cortex` profile (not the bundled Hermes `personal` profile). All cron jobs, skills, and configs are managed through the cortex layer.

### Cron Jobs Reference

> Content relocated to [`docs/cron-jobs-reference.md`](docs/cron-jobs-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## Troubleshooting

### Nginx started manually, systemd shows failed

When nginx is started outside systemd (e.g., by running `sudo nginx` directly), the ports are already bound when systemd tries to start it, causing `bind() failed (98: Unknown error)`. The service continues running fine, but won't auto-restart on reboot. Fix: stop the manual instance and start via systemd.

### Langfuse ClickHouse merge failures

The `langfuse-health-watchdog` reports ClickHouse `TotalMergeFailures` climbing with background executor threads stuck. Root cause: system log tables (trace_log, text_log) accumulate 4+ GiB of data. When merges fail due to memory pressure and the executor backlog grows, all 45 background threads can get stuck — unable to merge (memory), unable to free memory (stuck threads). Deadlock.

**Quick fix (nuke data volume, restart fresh):**
```bash
cd ~/langfuse
docker compose stop langfuse-worker langfuse-web clickhouse
docker compose rm -f clickhouse
docker volume rm langfuse-clickhouse-data
docker compose up -d clickhouse
# Wait for healthy, then:
docker compose up -d langfuse-worker langfuse-web
```
This drops ~75 MB of trace data (acceptable in staging). The low-memory config at `clickhouse-config.d/02-low-memory.xml` prevents recurrence by capping merge sizes (500 MB), cache (256/128 MB), and TTL-expiring system logs at 7 days.

**If system logs still grow fast:**
Reduce TTLs in `02-low-memory.xml`:
- `trace_log_ttl` → `1` (1 day instead of 7)
- `text_log_ttl` → `3` (3 days instead of 14)

**Full reference:** `ops/install/deploy/README-langfuse-clickhouse.md`

### 5. Governance & Quality

> Content relocated to [`docs/pipeline-reference.md`](docs/pipeline-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### 6. Performance Scorer

| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `llm-judge-scorer-weekday` | no_agent | `0 12,20 * * 1-5` | `llm-judge-scorer.py` | local |
| `llm-judge-scorer-weekend` | no_agent | `0 22 * * 0,6` | `llm-judge-scorer.py` | local |

### 7. Deployment-Specific

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above.

### Skill Collection Pipeline

The full skill lifecycle runs across all agents via the unified daily pipeline:

1. **Collect** — Every agent runs `agent-learning-collector` (no_agent, every 6h). First, mines recent sessions via `session-mine` to extract new lessons. Then collects skills delta, lessons delta, and session stats. Sends "Learning Report" to `inbox_moses`. Silent when nothing new (watchdog pattern).
2. **Evaluate + Upstream** — Moses runs `orch-skill-lifecycle` (LLM-driven, daily 04:00). Reads all agent reports from the bus, cross-references across agents, evaluates for consolidation/upstream candidates, patches skills, and pushes to the repo.

See [`docs/pipeline-reference.md`](docs/pipeline-reference.md) for the detailed pipeline architecture.

---

## Reference Docs

Previously inlined content moved to:

| Subject | Location |
|---------|----------|
| Ollama Model Tier, env vars, cron 3-tier | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Loop Governance setup, troubleshooting, full tables | [`docs/loop-governance-reference.md`](docs/loop-governance-reference.md) |
| Pipeline Reference (lessons, sessions, skills, memory, quality) | [`docs/pipeline-reference.md`](docs/pipeline-reference.md) |
| Fleet Reference (agent summary, cron jobs, auto-remediation) | [`docs/fleet-reference.md`](docs/fleet-reference.md) |
| Operations Reference (inbox architecture, offline code, rules) | [`docs/operations-reference.md`](docs/operations-reference.md) |
| Health monitoring, agent setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Symlink policy (Hermes vs Cortex layout) | [`docs/symlink-policy.md`](docs/symlink-policy.md) |
