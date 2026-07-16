# Agent Guidelines — Hermes Cortex

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. MCP server blocks write tools without a lock.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement that benefits other agents goes into `hermes-cortex`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

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
| `install.sh` | Single-command installer |
| `deploy/` | Langfuse + ClickHouse docker-compose |
| `.hermes-cortex/` | Agent infra: sessions, memory, skills.yaml |
| `agent-inbox-private/` | Git-backed agent message store |

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

    > **⚡ Pre-commit scoring hook** auto-creates a cycle on every commit. Use governance. `SKIP_SCORE=1` is emergencies only (abuse detection: 3/h warns, 6/24h blocks, 3 warnings locks permanently).

12. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip or fix inline.
14. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.
15. **Never print secrets in commands** — never pass secrets as literal strings in `terminal()` commands. Use `$(cat <file>)` subshell expansion so only the file path appears in the tool call. `printf`, `echo` with inline secret values, and `-u "user:pass"` are all forbidden patterns. <!-- Added 2026-07-13 -->
16. **Do not cut corners** — every skipped step compounds into a system failure. If a step feels optional, it is the most important one to do. Test from the deployed path, check sibling call paths, update docs, notify dependent agents. The right way is the only way.
17. **Be thorough** — verify every claim with tool output before delivering. A change is not complete until dependencies resolve, docs are updated, and the doctor runs clean. Half-done work erodes trust faster than slow work.

---

## Pre-Task Sequence — Mandatory Before Every Task

This is NOT optional. Every task starts with this exact sequence,
regardless of task size, urgency, or domain.

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

---

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

The worker reads from `~/.hermes-cortex/hermes-inbox.conf`:
```ini
BUS_URL=http://bus-host:8905
CORTEX_BUS_AUTH=<your-basic-auth>    (legacy: CORTEX_BASIC_AUTH)
AGENT_NAME=<your-name>
```

Also accepts `CORTEX_BUS_FALLBACK_URL` and `CORTEX_BUS_AUTH` (primary names). Old names `CORTEX_BUS_URL` and `CORTEX_INBOX_AUTH` are deprecated but still work as fallback.

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
| `service-recovery` | no_agent | `*/5 * * * *` | `service-recovery.py` | origin |
| `model-health-watchdog` | no_agent | `0 7 * * *` | `model-health-watchdog.py` | origin |

### 3. Knowledge & Memory
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `memory-to-brain-sync` | no_agent | `0 */6 * * *` | `memory-to-brain-sync.py` | local |
| `auto-save-sessions` | no_agent | `every 360m` | `auto-save-sessions.py` | local |
| `memory-pruning` | LLM+prompt | `0 4 * * 1` | (consolidation prompt) | origin |
| `harvest-lessons` | no_agent | `0 5 * * 1` | `harvest-lessons.sh` | origin |

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

The full skill lifecycle runs across all agents:

1. **Collect** — Every agent runs `collect-agent-skills.sh` every 6h, scanning both `~/.hermes/skills/` and `~/.hermes-cortex/skills/` for SKILL.md files not in the upstream repo. Custom skills are reported to Moses inbox (topic: `reports`).
2. **Request** — Weekly (Mon 2am), Moses runs `request-skill-reports.sh` to prompt all agents to share skills.
3. **Process** — Daily (3am), Moses runs `process-skill-reports.py` to compile incoming reports into a digest.
4. **Evaluate** — Weekly (Tue 9am), an LLM-driven `skill-evaluate` cron reviews each custom skill for quality, structure, and upstreaming potential.
5. **Upstream** — Skills approved for sharing are added to `hermes-cortex/skills/<category>/<name>/SKILL.md` and deployed fleet-wide via `cortex-update.sh` sync.

See [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md) for the manifest-based skill loading system (Titus).

---

## Luke's Deployment: Profile Structure

### Active Profiles

This deployment uses the `hermes-cortex` profile (not the bundled Hermes `personal` profile). All cron jobs, skills, and configs are managed through the cortex layer.

### Cron Jobs Reference

| Name | Type | Schedule | Purpose |
|------|------|----------|---------|
| remediation-sensor | no_agent | */5 * * * * | Detect system issues |
| system-alert-watchdog | no_agent | */30 * * * * | Monitor system alerts |
| service-recovery | no_agent | */5 * * * * | Auto-recover services |
| memory-to-brain-sync | no_agent | 0 */6 * * * | Sync memory to gbrain |
| hermes-update | no_agent | 23 22 * * * | Nightly Hermes update |
| gbrain-nightly-dream | no_agent | 0 3 * * 6 | Weekly gbrain dream |
| gbrain-update-sync | no_agent | 0 2 * * 0 | Weekly gbrain sync |
| hermes-cortex-sync | no_agent | 33 22 * * * | Nightly cortex sync |
| harvest-lessons | no_agent | 0 5 * * 1 | Weekly lesson harvest |
| memory-pruning | LLM+prompt | 0 4 * * 1 | Weekly memory prune |
| auto-save-sessions | no_agent | every 360m | Session persistence |
| agent-daily-bible-reading | no_agent | 0 1 * * * | Daily scripture reading |
| threat-pipeline | no_agent | 0 5 * * * | Daily nginx threat update |
| agent-daily-soul-refinement | LLM+skill | 0 23 * * * | Daily SOUL.md refinement |
| llm-judge-scorer-weekday | no_agent | 0 12,20 * * 1-5 | Weekday LLM evaluation |
| llm-judge-scorer-weekend | no_agent | 0 22 * * 0,6 | Weekend LLM evaluation |
| offline-code-index | no_agent | 0 5 * * 0 | Weekly offline code index |
| model-health-watchdog | no_agent | 0 7 * * * | Daily model health check |
| agent-remediate-apply | no_agent | */10 * * * * | Apply remediation fixes |
| scoring-activity-watchdog | no_agent | 0 14,20 * * * | Monitor scoring activity |
| skill-miner | no_agent | 0 6 * * 1 | Weekly skill mining |
| agent-weekly-loop-eval | LLM+skill | 0 9 * * 1 | Weekly loop evaluation |
| agent-ip-submission | no_agent | */30 * * * * | Submit IP to threat service |
| agent-apply-fixes | no_agent | */10 * * * * | Apply fix markers |
| cron-quality-watchdog | no_agent | */10 * * * * | Monitor cron output quality |
| session-cache-build | no_agent | 0 5 * * 1 | Weekly session cache build |
| agents-md-prune-scan | no_agent | 0 4 * * 1-6 | Daily AGENTS.md prune scan |
| agents-md-prune-apply | LLM+prompt | 30 4 * * 1-6 | Daily AGENTS.md prune apply |
| governance-auditor | no_agent | 0 */6 * * * | Governance compliance check |
| collect-agent-skills | no_agent | 0 */6 * * * | Collect skill usage data |
| send-skill-report | no_agent | 30 */6 * * * | Send skill reports |
| langfuse-health-watchdog | no_agent | 0 * * * * | Langfuse ClickHouse health |
| agent-fixer-workday | LLM+skill | 0 9-17 * * 1-5 | Auto-remediation workday |
| agent-fixer-evening | LLM+skill | 0 18,20,22 * * 1-5 | Auto-remediation evening |
| agent-fixer-overnight | LLM+skill | 0 3 * * 1-5 | Auto-remediation overnight |

---

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

The full skill lifecycle runs across all agents:

1. **Collect** — Every agent runs `collect-agent-skills.sh` every 6h, scanning both `~/.hermes/skills/` and `~/.hermes-cortex/skills/` for SKILL.md files not in the upstream repo. Custom skills are reported to Moses via the Agent Bus (topic: `reports`).
2. **Request** — Weekly (Mon 2am), Moses runs `request-skill-reports.sh` to prompt all agents to share skills.
3. **Process** — Daily (3am), Moses runs `process-skill-reports.py` to compile incoming reports into a digest.
4. **Evaluate** — Weekly (Tue 9am), an LLM-driven `skill-evaluate` cron reviews each custom skill for quality, structure, and upstreaming potential.
5. **Upstream** — Skills approved for sharing are added to `hermes-cortex/skills/<category>/<name>/SKILL.md` and deployed fleet-wide via `cortex-update.sh` sync.

See [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md) for the manifest-based skill loading system (Titus).

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
