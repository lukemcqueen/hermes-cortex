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
| `agent-inbox-private/` | Git-backed agent message store (deprecated — file-based fallback; active messaging is PGMQ Agent Bus) |

## Skill loading

**Every session start:** read `.hermes-cortex/skills.yaml` and load all `always` skills via `skill_view(name)`. Before each task, classify with `agent-flow`, then load `on_task` skills matching the classification.

Skills live in a single global location (`~/.hermes/skills/`) — no drift, no
stale copies across repos. To add a fleet-wide skill, upstream it to
`hermes-cortex/skills/<category>/<name>/SKILL.md`.

Documentation: [`docs/skills-manifest-reference.md`](docs/skills-manifest-reference.md)

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

12. **Tests/TDD/scoring are always the default.** Only opt-outs: `"skip tests"`, `"read-only"`, `"throwaway prototype"`, `"just check/look at"`.
13. **Tag discovered issues as follow-ups** — document as `pending` todo, finish current work, then return. Never silently skip or fix inline.
14. **Pull before push** — `git pull --rebase origin <branch>` before any `git push`.
15. **Never print secrets in commands** — never pass secrets as literal strings in `terminal()` commands. Use `$(cat <file>)` subshell expansion so only the file path appears in the tool call. `printf`, `echo` with inline secret values, and `-u "user:pass"` are all forbidden patterns. <!-- Added 2026-07-13 -->
16. **Do not cut corners** — every skipped step compounds into a system failure. If a step feels optional, it is the most important one to do. Test from the deployed path, check sibling call paths, update docs, notify dependent agents. The right way is the only way.
17. **Be thorough** — verify every claim with tool output before delivering. A change is not complete until dependencies resolve, docs are updated, and the doctor runs clean. Half-done work erodes trust faster than slow work.

18. **Never change the engine when the complaint is about delivery.** If the issue is wrong output destination or too much noise, fix the delivery configuration (`deliver`, [SILENT] protocol) — not the cron mode (`no_agent` ↔ LLM-driven). Diagnose the delivery pipeline before touching the architecture. See the `cron-job-management` skill's `cron-delivery-pipeline.md` reference.

19. **Never ask permission to fix what you broke.** If your action caused a problem, fix it — don't ask the user if you should. Revert, correct, and report. Asking "should I fix this?" wastes a turn and forces the user to manage your recovery.

---

## Pre-Task Sequence — Mandatory Before Every Task

This is NOT optional. Every task starts with this exact sequence, regardless of task size, urgency, or domain.

### Step 1: Load Always Skills

Read `.hermes-cortex/skills.yaml` (or `skills.yaml` in the project root). Call `skill_view(name)` for every skill in the `always` section.

These skills define HOW you think and work — they are active context for the entire task, not one-time loads.

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

Load `agent-flow` (already loaded from Step 1). Match the request against the 12 workflow patterns. This determines toolset, output format, and checklist.

### Step 4: Load On-Task Skills

After classification, read `.hermes-cortex/skills.yaml` again and call `skill_view(name)` for every skill in the `on_task` section matching your classification. Also call `skills_list()` for the relevant category to discover skills not in the manifest.

### Step 5: Call Survey-Before-Action

Call `skill_view(name="survey-before-action")` and run its checklist BEFORE creating any file, writing any code, or running any command. Search for existing resources first.

### Step 6: Work

Execute the task using the loaded skills, following the chosen reasoning pattern and the classified workflow pattern's checklist.

### Step 7: Reflexion Check Before Delivery

After completing the work but BEFORE presenting results:
1. Load `reflexion-check` and run the five-question audit
2. Score confidence (HIGH / MEDIUM / LOW / ZERO)
3. If LOW or ZERO: fix before delivering

### Step 8: Change Checklist Before End Change

For code/config/cron changes: load `change-checklist` and run all phases before calling end_change(). Phase 6 (Reflexion) is mandatory.

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

**Enforcement:** The MCP server's `loop-gov-mcp.py` blocks write tools unless a lock is active. Pre-commit hook auto-creates a scoring cycle on every commit. No script, no config, no cron change happens outside governance.

---

## Luke's Deployment: Profile Structure

### Active Profiles

This deployment uses the `hermes-cortex` profile (not the bundled Hermes `personal` profile). All cron jobs, skills, and configs are managed through the cortex layer.

### Cron Jobs Reference

| Name | Type | Schedule | Purpose |
|------|------|----------|---------|
| remediation-sensor | no_agent | */5 * * * * | Detect system issues |
|| inbox-flag | no_agent | */10 * * * * | Flag new bus messages (file-based fallback) |
| system-alert-watchdog | no_agent | */30 * * * * | Monitor system alerts |
| service-recovery | no_agent | */5 * * * * | Auto-recover services |
| memory-to-brain-sync | no_agent | 0 */6 * * * | Sync memory to gbrain |
|| inbox-sensor | no_agent | */10 * * * * | Detect bus activity |
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
|| agent-bus | LLM+prompt | */2 * * * * | Process Agent Bus messages |
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
|| inbox-depth-watchdog | no_agent | */1 * * * * | Monitor bus backlog depth |
| agent-fixer-workday | LLM+skill | 0 9-17 * * 1-5 | Auto-remediation workday |
| agent-fixer-evening | LLM+skill | 0 18,20,22 * * 1-5 | Auto-remediation evening |
| agent-fixer-overnight | LLM+skill | 0 3 * * 1-5 | Auto-remediation overnight |

---

## Troubleshooting

### Nginx started manually, systemd shows failed

When nginx is started outside systemd (e.g., by running `sudo nginx` directly), the ports are already bound when systemd tries to start it, causing `bind() failed (98: Unknown error)`. The service continues running fine, but won't auto-restart on reboot. Fix: stop the manual instance and start via systemd.

### Langfuse ClickHouse merge failures

The `langfuse-health-watchdog` reports ClickHouse `TotalMergeFailures`. This is a known Langfuse/ClickHouse issue. Check the watchdog output at `~/.hermes/cron/output/2df43e4b224a/` for details.

### 4. Agent Bus Processing
| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `inbox-depth-watchdog` | no_agent | `*/1 * * * *` | `bus/bus-depth-watchdog.sh` (file-based fallback) | local |
| `inbox-sensor` | no_agent | `*/10 * * * *` | `bus/bus-sensor.py` (PGMQ bus) | local |
| `inbox-flag` | no_agent | `*/10 * * * *` | `bus/bus-flag.py` (file-based fallback) | local |
| `agent-bus` | LLM | `*/2 * * * *` | (Agent Bus decision prompt + depth watchdog context) | origin |

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
| Operations Reference (bus architecture, offline code, rules) | [`docs/operations-reference.md`](docs/operations-reference.md) |
| Health monitoring, agent setup | [`docs/setup-reference.md`](docs/setup-reference.md) |
| Symlink policy (Hermes vs Cortex layout) | [`docs/symlink-policy.md`](docs/symlink-policy.md) |
