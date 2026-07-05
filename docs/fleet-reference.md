# Fleet Reference (Luke's Deployment)

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

This document contains fleet-specific guidance for Luke's multi-agent
orchestration setup. It was relocated from `AGENTS.md` to keep the root
agent guidelines focused on general Hermes Cortex usage.

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

**Why GitHub Issues:** Cross-machine bridge — Titus writes repo comments, Moses reads via `gh api`. Natural audit trail.

**Why this matters:** Prevents context-switching, builds historical record of focus areas, creates natural daily rhythm.

---

## Luke's Deployment: Daily Priority Check-in

### Processing pipeline

| Step | Skill | Description |
|------|-------|-------------|
| Elicit | `requirements-elicitation` | Structured requirements gathering from user goals |
| Review | `architecture-review` | Architecture review with weighted decision matrix |
| Spec | `product-requirements` | 1-page PRD — problem, solution, constraints, open questions |
| Slice | `story-decomposition` | Break feature into independently deliverable stories |
| Build | `change-test-loop` | LEARN-RED-GREEN-REFACTOR with lesson-aware memory |
| Review | `code-review` | Pre-commit review: security, quality, auto-fix |

---

## Luke's Deployment: Cron Jobs Reference

| Cron | Schedule | Type | Purpose |
|------|----------|------|---------|
| `agent-auto-remediate` | `*/30 * * * *` | LLM+skill | Auto-fix cron/inbox/service issues |
| `remediation-sensor` | `*/5 * * * *` | no_agent | Companion diagnostics sensor |
| `service-recovery` | `*/5 * * * *` | no_agent | Auto-restart crashed services |
| `hermes-update` | `23 22 * * *` | no_agent | Daily Hermes upgrade + config migrate |
| `hermes-cortex-sync` | `33 22 * * *` | no_agent | Daily repo pull + tool re-sync |
| `system-alert-watchdog` | `*/30 * * * *` | no_agent | Resource threshold alerts |
| `agent-cron-failure-scanner` | `*/30 * * * *` | no_agent | Scans ALL cron outputs for recent failures (last 90 min) |
| `inbox-sensor` | `*/10 * * * *` | no_agent | Detect new broadcast messages |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | Memory persistence to gbrain |
| `score-auditor` | `0 */6 * * *` | no_agent | Scans for unscored changes |
| `gbrain-nightly-dream` | `0 3 * * 6` | no_agent | Weekly gbrain knowledge enrichment |
| `gbrain-update-sync` | `0 2 * * 0` | no_agent | Weekly gbrain update + health check |
| `harvest-lessons` | `0 5 * * 1` | no_agent | Weekly lesson harvesting |
| `memory-pruning` | `0 4 * * 1` | LLM+prompt | Weekly memory consolidation |
| `auto-save-sessions` | `every 360m` | no_agent | Session state auto-save |
| `agent-daily-bible-reading` | `0 1 * * *` | LLM+skill | Daily Bible reading |
| `agent-daily-soul-refinement` | `0 23 * * *` | LLM+skill | Daily soul refinement |
| `llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | Weekday trace quality scoring |
| `llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | Weekend trace quality scoring |
| `offline-code-index` | `0 5 * * 0` | no_agent | Weekly corpus index refresh |
| `process-mcp-agent-inbox-messages` | `*/30 * * * *` | LLM | Read + process new inbox messages |
| | | | |
| **Orchestrator-only (Moses primary, Esther backup):** | | | |
| `orch-team-health` | `*/10 * * * *` | no_agent | Cross-agent health polling |
| `orch-team-messages` | `*/10 * * * *` | no_agent | Flag urgent agent messages |
| `orch-process-agent-messages` | `*/10 * * * *` | LLM | Process inbox remediation markers |

### Cron naming convention

When creating a new cron, prefix it to signal scope so other agents know whether to install it:

| Prefix | Meaning | Example |
|--------|---------|---------|
| `orch-*` | **Orchestrator-only** — runs only on the orchestrator (Moses) and backup | `orch-team-health` |
| `agent-*` | **LLM-driven** — agent reasons each tick; installable on any machine | `agent-auto-remediate` |
| `local-*` | **This server only** — NOT shared with or installed on peer agents. Combine with `agent-` as `local-agent-*` for LLM-driven local crons. | `local-agent-daily-news-brief` |
| no prefix | **General no_agent** — safe for any agent to run, no LLM tokens used | `remediation-sensor` |

**Rule:** If a cron should stay on one machine and never appear on Titus, Gisu, or Joseph, prefix it `local-*`.

**Management:**
```bash
hermes cron list
bash ~/.hermes/scripts/install-crons.sh          # install/update all
bash ~/.hermes/scripts/install-crons.sh --force  # recreate all
bash ~/.hermes/scripts/install-crons.sh --dry-run
bash ~/.hermes/scripts/install-crons.sh --uninstall
```

---

## Fleet Reference

### Agent summary

|| Agent | Role | Host | Services | Inbox method | Health auth |
||-------|------|------|----------|-------------|-------------|
|| Moses | Primary orchestrator | moses-server (Linux) | Gateway + nginx proxy :13004 | HTTP poll (self) | Auth required |
|| Esther | Backup orchestrator | worker-5 (Linux) | Gateway + nginx proxy :14004 | HTTP poll (+bkup inbox) | Auth required |
|| Gisu | Remote server | worker-3 (Linux) | Health endpoint :13007 | HTTP poll → Moses inbox | Auth required |
|| **Joseph** | **Remote server** | **worker-2 (Linux)** | **Health endpoint :12007** | **HTTP poll → Moses inbox** | **No auth** |
|| Kustos | Remote server | worker-4 (Linux) | Health endpoint :13007 | HTTP poll → Moses inbox | Auth required |
|| Titus | macOS developer | LAM2 (Apple M1, 16GB) | Client only; Ollama crons use qwen2.5-coder:7b-iq3_xs | Push health to Moses inbox | N/A |

> **Health endpoint auth:** All server health ports (13007, 14004) require HTTP basic auth except **Joseph (:12007)** — it's health-only and Moses polls it directly. See `hermes-services.conf` for the auth config per server block.

### Auto-remediation components

All in `src/scripts/`, installed by `install.sh` + `install-crons.sh`:

| Script | Type | Schedule | Purpose |
|--------|------|----------|---------|
| `cron-auto-remediate.sh` | Shell | On-demand | Diagnostics + fix actions (fix-missing, fix-git, fix-perms, fix-purge) |
| `system-alert-watchdog.py` | no_agent | Every 10m | Resource alerts + auto-cleanup |
| `service-recovery.py` | no_agent | Every 5m | Auto-restart nginx, Ollama, gbrain, Langfuse |
| `orch-team-messages.sh` | no_agent | Every 10m | Flags agent error messages with remediation markers |
| `agent-auto-remediate` (skill) | LLM cron | Every 5m | Checks errored crons + inbox remediation, applies fixes |

**Skill:** `src/skills/devops/auto-remediation/SKILL.md`
**Setup:** Silent when healthy, brief when fixes applied, escalate after 3 failures.

### Esther setup (backup orchestrator)

```bash
# 1. Copy agent registry
cp ~/.hermes-cortex/src/agent-registry.json ~/.hermes/state/agent-registry.json
# 2. Install crons
bash ~/.hermes-cortex/src/scripts/install-crons.sh
# 3. Copy orchestrator-specific scripts
cp ~/hermes-cortex/src/scripts/orch-moses-inbox-remediate.sh ~/.hermes/scripts/
cp ~/hermes-cortex/src/scripts/orch-weekly-auto-fix.py ~/.hermes/scripts/
# 4. Create orch-process-agent-messages cron (see agent-registry.json)
# 5. Start gbrain autopilot
gbrain autopilot --repo ~/brain/default --interval 300 &
# 6. Fix score-cycle symlink (verify.sh expects this)
ln -sf ~/.hermes-cortex/tools/loop-governance/score_cycle.py ~/.local/bin/score-cycle
```

**Known false positives:**
- `system-heartbeat` exits 1 with `❌ gbrain sync daemon: DOWN` on Linux (macOS-only service)
- Loop governance `verify.sh` reports 1 warning about CLI symlink until step 6 above is done

### All timestamps in KST (UTC+9)

All monitoring scripts output timestamps in Seoul time. Affects: `orch-team-health.py`, `system-alert-watchdog.py`, `service-recovery.py`, `orch-team-messages.sh`, and all cron outputs.
