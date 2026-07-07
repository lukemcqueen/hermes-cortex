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

**What this repo is:** A public installer + skill set for [Hermes Agent](https://hermes-agent.nousresearch.com). Gets you Ollama, gbrain (PGLite), Langfuse, Cortex Dashboard, brain dirs, gbrain sync daemon, utility scripts.

### Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Guides, templates, reference docs |
| `install.sh` | Single-command installer |
| `deploy/` | Langfuse + ClickHouse docker-compose |
| `.hermes-cortex/` | Agent infra: sessions, skills, memory |
| `agent-inbox-private/` | Git-backed agent message store |

### Project Directory Convention

```
project-root/
├── .hermes-cortex/           # Agent infra (hidden, near code)
│   ├── sessions/current.md   # Active session state
│   ├── sessions/archive/     # Timestamped snapshots
│   ├── memory/               # Gitignored — per-user MEMORY.md, USER.md
│   └── skills/               # Tracked project-specific skills
├── AGENTS.md                 # Stays at root
└── docs/                     # Stays at root
```

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
8. **Keep working until done** — don't stop after a stub or plan.
9. **Use tools, not descriptions** — every response must contain tool calls or a final result.
10. **Score every change** — every code/config/script edit logged to loop-governance DB.

    > **⚡ Pre-commit scoring hook** auto-creates a cycle on every commit. Never bypass. `SKIP_SCORE=1` is emergencies only.

11. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
12. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip or fix inline.
13. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.

---

## Loop Governance — Mandatory Agent Workflow

**Every change requires this sequence:**

### Before work
```python
mcp_loop_governance_cache_search(query="<what you are about to do>")
```

### After each logical change
```python
mcp_loop_governance_cycle_query(task_id="<descriptive-name>")
mcp_loop_governance_feedback_accept(cycle_id=N, note="verified: <how>")
# OR if wrong:
mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="MOVE_ON", note="...")
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

**Mandatory sections:** SOUL.md: Identity, Mission, Behavioral Principles (Loop Gov + Inbox Framework), Communication, Scripture. AGENTS.md: Execution Contract, Loop Gov, Inbox Framework, Doc Freshness.

---

## Agent Cron Management

Only Moses has `cronjob` MCP tool. Others request via inbox with subject `🔧 CRON: create|update|remove`. Fields: `CRON_NAME`, `CRON_SCHEDULE`, `CRON_PROMPT`/`CRON_SCRIPT`, `CRON_DELIVER`, `CRON_REASON`.

**Universal crons** (installed by `install-crons.sh` on every agent):

| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `agent-auto-remediate` | LLM | `*/30 * * * *` | `auto-remediation` | origin |
| `remediation-sensor` | no_agent | `*/5 * * * *` | `remediation-sensor.py` | local |
| `system-alert-watchdog` | no_agent | `*/30 * * * *` | `system-alert-watchdog.py` | origin |
| `agent-cron-failure-scanner` | no_agent | `*/30 * * * *` | `agent-cron-failure-scanner.py` | local |
| `service-recovery` | no_agent | `*/5 * * * *` | `service-recovery.py` | origin |
| `inbox-sensor` | no_agent | `*/10 * * * *` | `inbox-sensor.py` | local |
| `score-auditor` | no_agent | `0 */6 * * *` | `score-auditor.py` | origin |
| `memory-to-brain-sync` | no_agent | `0 */6 * * *` | `memory-to-brain-sync.py` | local |
| `llm-judge-scorer-weekday` | no_agent | `0 12,20 * * 1-5` | `llm-judge-scorer.py` | local |
| `offline-code-index` | no_agent | `0 5 * * 0` | `offline_code_index_cron.sh` | local |
| `model-health-watchdog` | no_agent | `0 7 * * *` | `model-health-watchdog.py` | origin |
| `agents-md-prune-scan` | no_agent | `0 4 * * 1-6` | `agents-md-prune-scan.py` | local |
| `agents-md-prune-apply` | LLM | `30 4 * * 1-6` | prompt: review scan + apply moves | origin |
| `process-mcp-agent-inbox-messages` | LLM | `0 6-23 * * *` | inbox poll + failure check | origin |

Run `bash ~/hermes-cortex/src/scripts/install-crons.sh --dry-run` to see what's missing. LLM crons pinned via `pin_cron_model()`.

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
