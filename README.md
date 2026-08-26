# 🧠 Hermes Cortex

> *An open-source installer, skill set, and fleet management system for your personal Hermes AI agent.*
> *Privacy-first, offline-capable, multi-agent orchestration — runs on your own hardware.*

**Version: 2.0.0** · [![GitHub](https://img.shields.io/github/license/lukemcqueen/hermes-cortex)](LICENSE) · [Hermes Agent](https://hermes-agent.nousresearch.com)

![Hermes Cortex](docs/assets/avatar.png)

**Hermes Cortex** is a self-contained system installer and public skill set for the [Hermes Agent](https://hermes-agent.nousresearch.com) runtime — but it's grown into much more. It's a **multi-agent fleet management platform**, a **governance engine**, a **self-healing operations system**, and a **deep knowledge stack**, all running on your own hardware with zero cloud dependency.

> **Why it exists:** Hermes Cortex turns a single Hermes Agent into a governed, self-healing fleet. It's the only agent harness where change discipline is **enforced at the tool level** — not suggested — where a crashed service **fixes itself before you wake up**, where the knowledge brain **works fully offline**, and where a second orchestrator **takes over the moment the first one blinks**. No cloud, no lock-in, no babysitting.

> **Prerequisite:** [Hermes Agent](https://hermes-agent.nousresearch.com) must be installed first. This project adds skills, services, and infrastructure on top of it.

---

## 🎁 What You Can Take From This Repo

This is a **working enterprise-grade agentic harness**, not just a skill pack.
Every pattern below is implemented in real code with exact file paths — steal
the pieces you need:

| # | Take-away | Where | What you get |
|---|-----------|-------|--------------|
| 1 | 🛡️ **Bad-actor IP blocklist** | [`ops/install/deploy/nginx/blocked_ips.add`](ops/install/deploy/nginx/blocked_ips.add) | **4,233 evidence-based blocked IPs**, one per line — drop into nginx/fail2ban/UFW today |
| 2 | 🤝 **Agent-to-agent messaging** | [`ops/scripts/lib/cortex_bus.py`](ops/scripts/lib/cortex_bus.py) · [protocol](docs/fleet-update-protocol.md) | Production A2A over Postgres PGMQ — `bus_send`/`bus_read`/`bus_archive`, correlation IDs, no Kafka/Redis |
| 3 | 💰 **RAG + semantic caching** | [`ops/web-cache/web_cache.py`](ops/web-cache/web_cache.py) · [mycortex](docs/design/mycortex-DESIGN.md) | sqlite-vec + Ollama cache that answers queries **before** the LLM — cuts token spend, works offline |
| 4 | 🔒 **Enforced change governance** | [`plugins/governance-enforcer/`](plugins/governance-enforcer/) · [reference](docs/loop-governance-reference.md) | Change discipline **blocked at the tool level**, not suggested — no bypass flags, TDD Iron Law, adversarial verification |
| 5 | 🤖 **Self-healing operations** | `ops/scripts/remediation/` · [reference](docs/fleet-reference.md) | sensor → marker → fixer pipeline that repairs crashes before you wake up |
| 6 | 🕵️ **Threat pipeline** | [`ops/scripts/manage/agent-nginx-threat-pipeline.sh`](ops/scripts/manage/agent-nginx-threat-pipeline.sh) | Daily log scan → fail2ban bans → new blocklist entries, evidence-based |

👉 **Full patterns guide with reading order:** [`docs/PATTERNS.md`](docs/PATTERNS.md) —
each pattern explains *how it works*, the *minimal code to copy*, and the
*suggested reading order* for the source files.

---

## 🌟 What Makes This Special

### 🧩 Multi-Agent Fleet Architecture

Hermes Cortex runs a coordinated team of specialized AI agents, each with distinct role, memory, and toolset:

| Agent | Role | Responsibility |
|-------|------|---------------|
| **Moses** 🗂️ | Orchestrator | Fleet health, cron management, infrastructure, governance |
| **Esther** 👑 | Backup Orchestrator | Cover for Moses during downtime |
| **Titus** 🏗️ | DevOps | Service health, ClickHouse ops, recovery automation |
| **Joseph** ⚙️ | Server Agent | Full-stack infra: nginx, services, web ops, fleet updates |
| **Kustos** 🛡️ | Security | Threat detection, blocklist management, access control |
| **Gisu** 💬 | Communications | Inbox routing, message triage, cross-agent coordination |

> **Agent Taxonomy:** Agents fill three role tiers. **Orchestrators** (Moses, Esther) run bus-based fleet orchestration scripts (`orch-bus-*`) and manage the update pipeline. **Server-agents** (Joseph, Kustos, Gisu) run the full Hermes Cortex stack with inbox polling and bus health checks. **Dev-agents** (Titus — macOS) run the agent message handler to process fleet commands via their bus inbox.

Agents communicate via a **PGMQ-based Agent Bus** with A2A (Agent-to-Agent) protocol — Postgres-backed message queues with auth, health monitoring, and fallover. No shared state, no race conditions.

### 🔒 Loop Governance — Enforced Change Discipline

Every code change follows a mandatory workflow that's **enforced at three levels**:

```
begin_change() → work → cycle_query() → feedback_accept() → end_change()
```

1. **🔴 MCP Enforcement** — The governance enforcer plugin blocks all write tools (`patch`, `write_file`, `terminal`) if no active lock exists
2. **⚡ Pre-Commit Hook** — Every `git commit` runs `score-cycle` against the diff, logs to the governance DB, and validates AGENTS.md integrity
3. **🕵️ Cron Auditor** — `governance-auditor` runs every 6h scanning for unscored changes + cleaning stale locks (>12h)

The **`pre-commit score hook`** auto-scores each commit and runs the **mandatory adversarial verification gate** (A2 default, A4 for security/guard/hook/enforcer files) on every staged script. No `SKIP_SCORE=1` bypass — and no `--no-verify` to ship a hook-rejected change: it is logged and audited (`agent-no-verify-audit` cron). Fix the findings, then commit normally.

### 🤖 Auto-Remediation Pipeline

Issues fix themselves. The pipeline runs every 5 minutes:

```
remediation-sensor → remediation markers → agent-remediate-apply → agent-fixer
```

Sensors detect problems (crashed services, broken configs, stale locks), write remediation markers, and specialized fixer agents apply the cure — all autonomously.

### 🩺 Self-Healing Operations

**~50 cron jobs per agent — a few hundred across the fleet** — keep the system healthy without human intervention:

| Category | Crons | What |
|----------|-------|------|
| **Health** | `orch-fleet-watchdog`, `system-alert-watchdog`, `model-health-watchdog`, `bus-health-check` | Every 5-30 min health checks across all agents |
| **Recovery** | `service-recovery`, `agent-remediate-apply`, `remediation-sensor` | Auto-restart crashed services, apply fixes |
| **Governance** | `governance-auditor`, `scoring-activity-watchdog` | Score tracking, lock cleanup, audit trails |
| **Messaging** | `cortex-bus-workday/evening/overnight` | Process cortex-bus messages on schedule |
| **Sync** | `hermes-cortex-sync`, `memory-to-brain-sync`, `agent-mycortex-sync` | Pull updates, persist memory, sync knowledge brain (every 15 min) |
| **Security** | `threat-pipeline`, `agent-ip-submission` | Block threats, report IPs |
| **Maintenance** | `memory-pruning`, `session-cache-build`, `orch-skill-lifecycle` | Weekly consolidation, daily skill lifecycle pipeline |
| **Content** | `agent-daily-bible-reading` *(opt-in)*, `orch-skill-lifecycle`, `agent-offline-code-index` | Daily spiritual reading (opt-in, marker `~/.hermes-cortex/bible-reading-enabled`), skill lifecycle (daily 04:00), code indexing |
| **Reports** | `orch-health-report` | Scheduled health briefings |

All crons follow the **silent-when-good** pattern — zero output when healthy, targeted alerts on state changes.

### 🧠 Deep Knowledge Stack

A cascade retrieval system that works with or without internet:

```
Agent query → web_cache (50μs) → kiwix ZIM (localhost:8080) → mycortex (RAG) → LLM (always)
```

- **Web Cache** — Semantic search cache (sqlite-vec + Ollama embeddings, ~200MB LRU) — saves API costs
- **Offline Knowledge** — Wikipedia, WikiMed, Wikivoyage, Wikibooks available locally via Docker ZIM server
- **Offline Code Assistant** — 520+ curated code snippets across 55+ topic areas and 30+ programming languages. `offline_code search` and `offline_code gen` work fully offline via Ollama. **Self-improving:** `offline_code learn` adds misses permanently.
- **Offline Reader** — Zero-dependency web UI (`python3 ops/offline/offline-reader.py`) for Bible (55+ languages), hymns, and wiki reference
- **mycortex** — Fleet knowledge brain: git repos as source of truth → shared Postgres index (FTS + pg_texample; pgvector semantic slice in v1.1) → thin Python CLI + 15-min cron sync. No daemon, no bun. **Inspired by an open-source Postgres-native knowledge-brain project (garrytan, MIT)** — the same Postgres-native knowledge-brain idea, re-architected with fail-closed RLS source isolation, per-host registration, and a PII federation gate. **Multi-tenant by construction:** each profile connects as its own `mycortex_reader_<profile>` role — RLS (keyed on `CURRENT_USER`) isolates tenants automatically, so a company brain scales to 100 profiles with zero policy changes. [Design doc](docs/design/mycortex-DESIGN.md) · [Multi-tenancy](docs/design/mycortex-multi-tenancy.md)

### 📊 Observability Stack

| Component | What | Tech Stack |
|-----------|------|-----------|
| Langfuse | LLM trace evaluation + scoring | ClickHouse, MinIO, Redis, Postgres (6 Docker containers) |
| Cortex Dashboard | Companion dashboard + system health | Flask, dark-theme, drag-and-drop |
| Orch Health Reporter | Cross-agent health summary (every 10 min) | Python watchdog |
| Scoring Activity Watchdog | Tracks scoring velocity per agent | Python watchdog |

### 🛡️ Security Stack

| Layer | Technology | What it does |
|-------|-----------|-------------|
| Network | **UFW/firewall** | Default-deny, port-range rules, SSH rate-limiting |
| Reverse Proxy | **nginx** | TLS + Basic Auth on all external ports, rate-limited (20 req/5s) |
| Ban System | **fail2ban** | 4 jails with escalation (1h→4wk): http-auth, limit-req, botsearch, bad-request |
| Access | **blocked_ips.add** | Shared cumulative blocklist maintained by ALL agents — append only |
| Pipeline | **nginx-threat-pipeline.sh** | Daily scan of nginx logs for attack patterns, auto-ban repeat offenders |
| Agent | **Governance Enforcer** | Blocks write tools without active governance lock |
| Agent | **Security Guidance Plugin** | 25 regex patterns (pickle.load, eval, yaml.load, etc.) — warns on dangerous code |

---

## 🏗️ Repository Architecture

The repository is organized into three layers, separating contracts from runtime
integration from operations:

| Layer | Directory | Purpose | Contents |
|-------|-----------|---------|----------|
| **Cortex Core** | `core/` | Schemas, governance, identity | Canonical type definitions, loop governance engine, agent identity contracts — zero runtime dependency |
| **Cortex Runtime** | `mcp-servers/`, `plugins/` | Hermes Agent bridge | MCP servers (`mcp-servers/`), governance enforcer plugin (`plugins/governance-enforcer/`) |
| **Cortex Ops** | `ops/` | Fleet operations | Installers (`ops/install/`), health scripts (`ops/scripts/health/`), watchdogs, offline stack, dashboard, cortex-bus, web cache, cron infrastructure |

The boundary is directional: **Core ← Runtime ← Ops**. Core knows nothing about
Hermes Agent. Runtime translates Core contracts into Hermes-compatible hooks and
plugins. Ops uses both to keep the fleet running.

This model makes it possible to swap the agent runtime (e.g. to LangGraph or
Temporal) by replacing only the Runtime Adapter layer.

Detailed breakdown: [`docs/architecture.md`](docs/architecture.md#-code-architecture-three-layer-model)

### 🧩 Optional Profiles

The repo ships with a neutral enterprise core. `profiles/` is the extension
point for personal or opinionated content — drop a layer in, symlink it into
the repo, and the fleet ships it. No profile ships by default; the core stays
neutral. See [`profiles/README.md`](profiles/README.md).

---

## 🚀 One-Command Install

> **🔒 Before installing:** Read the [Security Guide](docs/SECURITY.md).

### 🐧 New Linux Server — Full Bootstrap

Bare Ubuntu 24.04 VM? This single command does everything: installs Docker, Ollama, Hermes CLI, clones the repo, configures secrets, sets up nginx + Let's Encrypt SSL, hardens UFW and fail2ban, and verifies the stack.

```bash
# One-liner — no clone needed
curl -fsSL https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/ops/deploy/bootstrap.sh | bash
```

Expects: **Fresh Ubuntu 24.04 LTS** with SSH access. Interactive prompts for API keys and domain.
Takes: **8–15 minutes** (mostly model downloads).

> ⚠️ This is a *server bootstrap* — it installs Docker, nginx, Langfuse.
> For a laptop/client install, use `install.sh` below.

### 🖥️ Existing Machine — install.sh (macOS, Linux, WSL)

**Quick start (30 seconds):** Try the governance scoring tools:

```bash
# Pre-commit hook (auto-scoring via loop-governance MCP)
bash ~/hermes-cortex/ops/scripts/pre-commit-score
score-cycle --help          # ready to use
```

**Enforce scoring across all projects:**

```bash
# Layer 1 — pre-commit hook (blocks commits without scoring):
bash ops/scripts/install/install-score-hook.sh --all

# Layer 2 — SOUL.md directive (every Hermes session sees the rule):
echo -e "\n## Mandatory Directives\n**Score every change** — run \`score-cycle\` after every file edit." >> ~/.hermes/SOUL.md

# Layer 3 — cron auditor (checks every 6h for unscored changes + cleans stale locks):
bash ops/scripts/install-crons.sh --force
```

**Full install (5-15 min):**

```bash
# One-liner — no clone needed
curl -fsSL https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/ops/install/install.sh | bash

# Or clone for offline install / inspection:
git clone --depth 1 https://github.com/lukemcqueen/hermes-cortex.git ~/hermes-cortex
bash ~/hermes-cortex/ops/install/install.sh

# Check prerequisites only:
bash ~/hermes-cortex/ops/install/install.sh --check

# macOS — Laptop profile: lean, no Docker
CORTEX_PROFILE=laptop bash ~/hermes-cortex/ops/install/install.sh

# Linux — auto-detects systemd, apt/dnf/pacman
CORTEX_OS=linux bash ~/hermes-cortex/ops/install/install.sh

# Windows — uses winget/choco + scheduled tasks (limited)
CORTEX_OS=windows bash ~/hermes-cortex/ops/install/install.sh
```

### What `install.sh` does

| Step | What | Why |
|------|------|-----|
| 0 | **System Check** | Verifies OS, RAM, disk, Docker, network before touching anything |
| 1 | **Ollama** | Native installer per OS; bound to localhost; pulls embedding model |
| 2 | **Bun** | JavaScript runtime for build tooling |
| 3 | **mycortex** | Knowledge brain (markdown-in-git → shared Postgres index). **legacy brain decommissioned** |
| 4 | **Brain dirs** | `~/brain/{default,…}` with MECE schema + .gitignore + git init |
| 5 | **mycortex sync** | Sources config + `agent-mycortex-sync` cron (15-min) |
| 6 | **`/brain` plugin** | Hermes slash command for mycortex queries |
| 7 | **Scripts** | 260+ scripts: health checks, watchdogs, sync, governance, security |
| 8 | **Hermes memory** | Confirmed Hermes-owned — no cortex seed |
| 9 | **Skills** | 300+ shared skills installed to `~/.hermes/skills/` |
| 10 | **Hooks & MCP** | Scoring pre/post-commit hooks + loop-governance & task MCP servers |
| 11 | **Web Cache** | Semantic web result cache (sqlite-vec + Ollama) |
| 12 | **Observability** † | Langfuse (LLM traces) + Cortex Dashboard |
| 13 | **Offline Stack** | Cache cascade + kiwix ZIM + offline reader + code corpus |
| 14 | **nginx** † | Reverse proxy for Langfuse + Dashboard + hardening |
| 15 | **Plugin enable** | Auto-activates in Hermes config |
| 16 | **Hardening** | File-permission hardening on sensitive files |
| 17 | **Bootstrap Brain** | Verify + index brain sources |
| | *† Server profile only* | |
| | *The knowledge brain is **mycortex** — git repos as source of truth, shared Postgres index (FTS + pg_texample + pgvector), fail-closed RLS per profile. The legacy brain was DECOMMISSIONED 2026-08-02. See [design](docs/design/mycortex-DESIGN.md).* | |

### Configuration

```bash
export CORTEX_OS="linux"           # Auto-detected: darwin, linux, windows
export CORTEX_PROFILE="laptop"        # 'server' (default) or 'laptop'
export CORTEX_SOURCES="me,shared,default"  # Brain source names
export CORTEX_HOME="$HOME"          # User home directory
export HERMES_HOME="$HOME/.hermes"      # Hermes config directory
```

**OS Support:** macOS (launchd, Homebrew) · Linux (systemd, apt/dnf/pacman) · Windows (winget/choco, limited)

**Profiles:** `server` (full stack, Docker) · `laptop` (lean, no Docker — ideal for mobile)

### Multi-Person Setup

```bash
export CORTEX_SOURCES="me,family,shared,default"
bash ~/hermes-cortex/ops/install/install.sh
```

Each source has isolated memory and .gitignore. The `/brain` slash command adapts to whatever sources you configure.

---

## 🔄 Upgrading

To upgrade an existing Hermes Cortex installation:

```bash
cd ~/hermes-cortex
git pull --ff-only
bash ops/scripts/cortex-update.sh     # delta update (changed files only)
```

The `cortex-update.sh` script auto-detects what files changed and deploys only the deltas. For a full re-deployment:

```bash
bash ops/scripts/cortex-update.sh
```

> **Note:** After a major version upgrade, your agents should `/reset` their sessions to pick up new skills and plugin configurations.

---

## 🚚 Fleet Update Pipeline

The fleet update pipeline orchestrates coordinated rollouts across all agents using the Agent Bus:

```
Moses ──UPDATE_REQUEST──→ AgentBus ──→ Kustos (server-agent)
                     ──→ Gisu (server-agent)
                     ──→ Titus (dev-agent, polls inbox)
Kustos ──UPDATE_RESULT──→ AgentBus ──→ Moses
Gisu  ──UPDATE_RESULT──→ AgentBus ──→ Moses
Titus ──UPDATE_RESULT──→ AgentBus ──→ Moses
```

### Script Naming Convention

| Prefix | Scope | Location | Examples |
|--------|-------|----------|---------|
| `orch-bus-*` | Orchestrator-only (Moses, Esther) — deployed via `register_orch` | `ops/scripts/orch-bus/` | `orch-bus-fleet-dispatch`, `orch-bus-fleet-rollback`, `orch-bus-forwarder` |
| `agent-message-handler` | Agent-side inbox handler | `ops/scripts/agent/` | Polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK |
| `agent-*` | General agent crons | `ops/scripts/agent/` | `agent-inbox-poll` |

### Update Flow

1. **Pre-flight:** `orch-bus-readiness-check.py` verifies bus health, git state, and agent inbox queues
2. **Dispatch:** `orch-bus-fleet-dispatch.py` sends `UPDATE_REQUEST` to each server-agent's inbox
3. **Server-agents** poll their inbox, run `cortex-update.sh`, post `UPDATE_RESULT` back
4. **Dev-agents**: `agent-message-handler` polls their inbox, runs `cortex-update`, posts `UPDATE_RESULT`
5. **Rollback:** `orch-bus-fleet-rollback.py` reads dispatch state and sends `ROLLBACK_REQUEST` to failed agents
6. **Auth check:** `orch-bus-git-auth-check.py` verifies each agent can pull from the remote

### Shared Bus Library

All fleet scripts use `ops/scripts/lib/cortex_bus.py` — a shared HTTP API wrapper that reads `CORTEX_BUS_URL` / `CORTEX_BUS_FALLBACK_URL` from the environment. This eliminates the old pattern of `docker exec` calls into the Postgres container.

### Agent Message Handler (Inbox Polling)

Every agent gets an `agent-message-handler` cron (every 5 minutes) via `install-crons.sh`. It polls the agent's bus inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, and GIT_AUTH_CHECK messages, runs doctor on every tick, and reports health state changes. The handler script is deployed fleet-wide via `cortex-update.sh`.

---

## 🧠 Offline Knowledge Stack

| Scenario | `prep-offline` mode | Content | Size |
|----------|---------------------|---------|------|
| 🌴 **Jungle Travel** | `--mode=travel` | WikiMed + Wikivoyage + Simple Wiki + Wiktionary | ~6 GB |
| 🏗️ **Offline Dev** | `--mode=build` | Simple Wiki + Wikibooks + Wiktionary | ~7 GB |
| 📚 **Kid Learning** | `--mode=education` | Simple Wiki + Wikibooks + Wikivoyage | ~5 GB |

```bash
# After install, download content:
prep-offline --mode=travel

# Check system status:
offline_knowledge stats

# Query anything (works same online/offline):
offline_knowledge query "symptoms of malaria"
```

---

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, deep observability, and autonomous operations.

## 🔧 Key Scripts

| Script | Purpose |
|--------|---------|
| `ops/install/install.sh` | **Main installer** (moved from root in v2.0.0) |
| `ops/install/quick-start.sh` | Quickstart |
| `ops/scripts/cortex-update.sh` | Deploy scripts from repo to `~/.hermes/scripts/` — run after every `git pull` |
| `ops/scripts/manage/cortex-doctor.py` | System diagnostics, fix common issues |
| `ops/scripts/install/install-score-hook.sh` | Install/remove pre-commit scoring hooks on any repo |
| `ops/scripts/install-crons.sh` | Install/remove all 60+ agent cron jobs |
| `ops/scripts/manage/agent-hermes-update.sh` | Silent nightly update of Hermes Agent |
| `ops/scripts/manage/agent-hermes-cortex-sync.sh` | Nightly git pull of hermes-cortex repo |
| `ops/scripts/manage/agent-nginx-threat-pipeline.sh` | Daily nginx log scan + auto-ban repeat attackers |
| `ops/scripts/manage/deploy-blocked-ips.sh` | Deploy shared blocklist across fleet |
| `ops/scripts/manage/analyze-failures.py` | Analyze cron failure patterns |
| `ops/scripts/manage/template-diff-check.py` | Detect template drift across agents |

---

## 📚 Documentation

| Document | What it covers |
|----------|---------------|
| [Enterprise Patterns](docs/PATTERNS.md) | 🎁 **Start here** — reusable take-aways: bad-actor IP list, agent bus, RAG/token-cost caching, governance, self-healing, threat pipeline |
| [Security Guide](docs/SECURITY.md) | 🔒 Port risks, file permissions, firewall setup, recovery |
| [Architecture](docs/architecture.md) | System diagram, services, port map, design principles |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |
| [Loop Governance Reference](docs/loop-governance-reference.md) | Full governance workflow, scoring, enforcement layers |
| [Fleet Reference](docs/fleet-reference.md) | Agent summary, cron table, auto-remediation pipeline |
| [Setup Reference](docs/setup-reference.md) | Ollama config, env vars, cron tiers, model selection |
| [Pipeline Reference](docs/pipeline-reference.md) | Lessons, sessions, skills, memory, quality pipeline |
| [Operations Reference](docs/operations-reference.md) | Inbox architecture, offline code, rules engine |
| [Bus Scale Design](docs/design/bus-scale/stories.md) | Agent Bus scaling stories and capacity planning |
| [Offline Scenarios](docs/knowledge-isolation-architecture.md) | Using Hermes without internet |
| [AGENTS.md](AGENTS.md) | Agent execution contract, loop governance, inbox framework |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute to hermes-cortex |

---

> *"The more we get to know about our universe, the more the hypothesis that there is a Creator God, who designed the universe for a purpose, gains in credibility as the best explanation of why we are here."* — John Lennox

---

*Built by [@lukemcqueen](https://github.com/lukemcqueen) · Powered by 🦞 [Hermes Agent](https://hermes-agent.nousresearch.com) · Version `v2.0.0` · [MIT License](LICENSE) · See [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) for component attributions*
