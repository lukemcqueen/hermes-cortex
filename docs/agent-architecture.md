# 🏗️ Hermes Cortex — Agent Architecture & Role Model

> **🪪 Scope:** This document serves two audiences:
> - **General developers** — The role definitions, capability matrix, cron rules, and observability stack below are universal to Hermes Cortex and recommended for every multi-agent deployment.
> - **Luke's deployment** — Sections marked with `⚡` are specific to Moses's multi-machine setup (Moses orchestrator, peer agents, KST timezone, Telegram delivery). Treat these as examples you can adapt.
>
> Everything unmarked is general guidance — apply it to any multi-agent setup using this repo.

---

## Agent Roles

Every agent in the fleet belongs to one of four roles. The role determines which services run, which crons are installed, and what observability tools are available.

| Role | Example Agent | Platform | Purpose |
|------|--------------|----------|---------|
| **Orchestrator** | primary-orch | Linux | Fleet command, bus server, Postgres, skill lifecycle, fleet watchdogs |
| **Backup Orchestrator** | backup-orch | Linux | Hot standby — same capabilities, takes over if primary is down |
| **Server Agent** | server-agent-1 | Linux | Production services, health reporting, local remediation |
| **Dev Agent** | dev-agent-1 | macOS / Linux | Development work, multiple project repos, push-only bus |

---

## Capability Matrix

| Capability | Orchestrator | Backup Orch | Server Agent | Dev Agent |
|------------|:-----------:|:-----------:|:------------:|:---------:|
| **`cronjob` MCP tool** | ✅ | ✅ | ❌ | ❌ |
| **Bus access** | `host` | `host` | `client` | `client` |
| **Local bus daemon** | ✅ | ✅ | ❌ | ❌ |
| **Postgres (direct)** | ✅ | ✅ | ❌ | ❌ |
| **nginx** | ✅ | ✅ | ✅ | ❌ |
| **Ollama** | ✅ | ✅ | ✅ | ✅ |
| **GBrain** | ✅ | ✅ | ✅ | ✅ |
| **Langfuse** | ✅ | ✅ | ✅ | ✅ |
| **sudo access** | ✅ | ✅ | ✅ | optional |

### What each capability means

- **`cronjob` MCP tool** — Can create/update/remove cron jobs programmatically. Required for orchestrator-only crons and fleet management.
- **Bus access** — `host` = runs the bus server AND polls for messages. `client` = polls the shared bus for messages.
- **Local bus daemon** — Runs a local PGMQ server instance. Required for orchestrators.
- **Postgres (direct)** — Can connect to the shared Postgres database directly.
- **nginx** — Runs nginx as a reverse proxy for services (Langfuse, dashboard, bus).
- **Ollama** — Local LLM serving. All agents should have this for fallback/offline.
- **Langfuse** — LLM trace observability. All agents should send traces to the shared instance.
- **sudo access** — Can install system packages and manage systemd/Docker services.

---

## Services Per Role

### Orchestrator / Backup Orchestrator

```
┌─────────────────────────────────────────────────────────┐
│                  Orchestrator Server                     │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Hermes      │  │  Agent Bus   │  │  Postgres       │  │
│  │  Gateway     │  │  (PGMQ)      │  │  (shared DB)    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                  │           │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌───────┴────────┐  │
│  │  Langfuse   │  │  nginx       │  │  Ollama        │  │
│  │  (Docker)   │  │  (proxy)     │  │  (local LLM)   │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│                                                         │
│  Crons: install-crons.sh + install-orch-crons.sh        │
│  Observability: Langfuse (traces), cost tracking,       │
│                 LLM judge scorer, scoring watchdog       │
└─────────────────────────────────────────────────────────┘
```

### Server Agent

```
┌─────────────────────────────────────────────────────────┐
│                    Server Agent                          │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Hermes      │  │  Bus Client  │  │  Ollama         │  │
│  │  Gateway     │  │  (poll mode) │  │  (local LLM)    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────┘  │
│         │                │                              │
│  ┌──────┴──────┐  ┌──────┴───────┐                      │
│  │  nginx       │  │  GBrain      │                      │
│  │  (proxy)     │  │  (sync)      │                      │
│  └─────────────┘  └──────────────┘                      │
│                                                         │
│  Crons: install-crons.sh only (no orch-*)               │
│  Observability: Langfuse (traces), cost tracking,       │
│                 LLM judge scorer                         │
└─────────────────────────────────────────────────────────┘
```

### Dev Agent

```
┌─────────────────────────────────────────────────────────┐
│                     Dev Agent                            │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Hermes      │  │  Bus Client  │  │  Ollama         │  │
│  │  Gateway     │  │  (poll mode) │  │  (local LLM)    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────┘  │
│         │                │                              │
│  ┌──────┴────────────────┴───────┐  ┌────────────────┐  │
│  │  Project repos (hermes-cortex,│  │  GBrain        │  │
│  │  project-1, project-2, ...)   │  │  (sync)        │  │
│  └───────────────────────────────┘  └────────────────┘  │
│                                                         │
│  Crons: install-crons.sh (agent-* only)                 │
│  No: nginx, local bus daemon                            │
│  Observability: Langfuse (traces), cost tracking        │
└─────────────────────────────────────────────────────────┘
```

---

## Cron Installation Rules

| Prefix | Scope | Install Script | Doctor Validates | Runs On |
|--------|-------|---------------|-----------------|---------|
| `orch-*` | Orchestrator only | `install-orch-crons.sh` | `parse_orch_crons()` | Orchestrator, Backup Orch |
| `agent-*` | All agents | `install-crons.sh` | `parse_expected_crons()` | Every agent |
| `local-*` | This machine only | Manual `cronjob create` | Silently excluded by doctor | This machine |

- **Orchestrators** run BOTH `install-crons.sh` and `install-orch-crons.sh`
- **All other agents** run ONLY `install-crons.sh`
- The doctor validates the correct set based on which install scripts ran

---

## Observability Stack

### Langfuse — LLM Trace Observability

Every agent sends traces to the **shared Langfuse instance** running on the orchestrator. Each agent identifies itself via the `HERMES_LANGFUSE_ENV` environment variable.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Orchestrator │────▶│   Langfuse   │◀────│  Dev Agent   │
│  (traces)     │     │  (Docker)    │     │  (traces)    │
└──────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────┴───────┐
                    │  Server Agent │
                    │  (traces)     │
                    └──────────────┘
```

**Setup per agent:**
1. Generate a Langfuse API key pair (one per agent, identifiable by note)
2. Set `HERMES_LANGFUSE_*` env vars in `~/.hermes/.env`
3. Install `langfuse` Python SDK
4. Enable `observability/langfuse` plugin
5. Restart Hermes gateway

All crons that interact with Langfuse (judge scorer, scoring watchdog) use the same `agent-*` prefix so they run on every agent.

### Cost Tracking

Every agent with LLM cron jobs should have cost tracking active:

```bash
python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --force
```

This patches the Hermes scheduler to record per-run token usage and cost into `~/.hermes/cron/cron-costs.db`.

### LLM Judge Scorer

Runs on every agent with Langfuse. Scores traces using a local Ollama model and posts quality scores back to Langfuse:

- `agent-llm-judge-scorer-weekday` — Mon–Fri 12:00, 20:00
- `agent-llm-judge-scorer-weekend` — Sat–Sun 22:00

Quality dimensions: `helpfulness` (1-5), `clarity` (1-5), `depth` (1-5), `overall` (1-10).

### Scoring Activity Watchdog

`agent-scoring-activity-watchdog` runs daily at 14:00 and 20:00 on every agent:

1. **Scoring activity** — Checks loop-governance DB for cycles scored today; alerts if below expected threshold
2. **Cost check** — Queries cron-costs.db; alerts if daily cost exceeds `$0.25`
3. **Trace quality** — Queries Langfuse for traces scored below 4.0 in the last 48h

---

## Data Flow

### Inter-Agent Communication

```
┌──────────────┐     PGMQ Bus     ┌──────────────┐
│  Orchestrator │◀════════════════▶│  Server Agent │
│  (both mode)  │                 │  (poll mode)  │
└──────┬───────┘                 └──────────────┘
       │                                  ▲
       │ PGMQ Bus                         │ PGMQ Bus
       ▼                                  │
┌──────────────┐                 ┌────────┴───────┐
│  Backup Orch  │◀────────────────│  Dev Agent     │
│  (both mode)  │   PGMQ Bus     │  (push only)   │
└──────────────┘                 └────────────────┘
```

### Learning Report Pipeline

```
Every agent (every 6h):
  agent-learning-collector.py
    → Collects skills delta, lessons, session stats
    → Sends "Learning Report" to inbox_<orchestrator> via PGMQ

Orchestrator (daily at 4am):
  orch-skill-lifecycle (LLM cron)
    → Reads inbox for all Learning Reports
    → Processes skills, lessons, knowledge
    → Stores in gbrain
```

### Health Reporting Pipeline

```
Every agent (every 5 min):
  → Pushes health status to inbox_health_check via PGMQ

Orchestrator (every 5 min):
  orch-fleet-watchdog.py
    → Polls all agent health endpoints
    → Tracks active workflows
    → Detects stalled steps
```

---

## Configuration Per Role

### Orchestrator / Backup Orchestrator

```yaml
# ~/.hermes/config.yaml additions
browser:
  record_sessions: true
dashboard:
  show_token_analytics: true
display:
  show_cost: true
```

### Server Agent / Dev Agent

```yaml
# ~/.hermes/config.yaml additions
browser:
  record_sessions: true     # optional — enables session_search
dashboard:
  show_token_analytics: true
display:
  show_cost: true
```

---

## Quick Reference: What to Deploy Per Role

| Component | Orchestrator | Backup Orch | Server Agent | Dev Agent |
|-----------|:-----------:|:-----------:|:------------:|:---------:|
| Hermes Agent | ✅ | ✅ | ✅ | ✅ |
| Langfuse plugin | ✅ | ✅ | ✅ | ✅ |
| Cost tracking patches | ✅ | ✅ | ✅ | ✅ |
| LLM judge scorer | ✅ | ✅ | ✅ | ✅ |
| Scoring watchdog | ✅ | ✅ | ✅ | ✅ |
| Cron quality watchdog | ✅ | ✅ | ✅ | ✅ |
| Fleet watchdog | ✅ | ❌ | ❌ | ❌ |
| Skill lifecycle | ✅ | ❌ | ❌ | ❌ |
| Bus audit | ✅ | ✅ | ❌ | ❌ |
| Bus message tracker | ✅ | ✅ | ❌ | ❌ |
| Health reports | ✅ | ✅ | ❌ | ❌ |
|| GBrain | ✅ | ✅ | ✅ | ✅ |
|| GBrain | ✅ | ✅ | ✅ | ✅ |
| Local bus daemon | ✅ | ✅ | ❌ | ❌ |
| Postgres | ✅ | ✅ | ❌ | ❌ |

---

## Related Documents

- [`fleet-reference.md`](fleet-reference.md) — Deployment-specific cron schedules and agent registry
- [`agent-onboarding.md`](agent-onboarding.md) — Step-by-step setup for a new agent
- [`pipeline-reference.md`](pipeline-reference.md) — Data pipeline details (learning, health, skill lifecycle)
- [`architecture.md`](architecture.md) — Service topology and repository structure
