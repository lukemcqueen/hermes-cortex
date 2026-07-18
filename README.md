# 🧠 Hermes Cortex

> *An open-source installer, skill set, and fleet management system for your personal Hermes AI agent.*
> *Privacy-first, offline-capable, multi-agent orchestration — runs on your own hardware.*

**Version: 2.0.0** · [![GitHub](https://img.shields.io/github/license/fleet-operator/hermes-cortex)](LICENSE) · [Hermes Agent](https://hermes-agent.nousresearch.com)

![Hermes Cortex](docs/assets/avatar.png)

**Hermes Cortex** is a self-contained system installer and public skill set for the [Hermes Agent](https://hermes-agent.nousresearch.com) runtime — but it's grown into much more. It's a **multi-agent fleet management platform**, a **governance engine**, a **self-healing operations system**, and a **deep knowledge stack**, all running on your own hardware with zero cloud dependency.

> **Prerequisite:** [Hermes Agent](https://hermes-agent.nousresearch.com) must be installed first. This project adds skills, services, and infrastructure on top of it.

---

## 🌟 What Makes This Special

### 🧩 Multi-Agent Fleet Architecture

Hermes Cortex runs a coordinated team of specialized AI agents, each with distinct role, memory, and toolset:

| Agent | Role | Responsibility |
|-------|------|---------------|
| **Moses** 🗂️ | Orchestrator | Fleet health, cron management, infrastructure, governance |
| **Esther** 👑 | Backup Orchestrator | Cover for Moses during downtime |
| **Titus** 🏗️ | DevOps | Service health, ClickHouse ops, recovery automation |
| **Kustos** 🛡️ | Security | Threat detection, blocklist management, access control |
| **Gisu** 💬 | Communications | Inbox routing, message triage, cross-agent coordination |

> **Agent Taxonomy:** Agents fill three role tiers. **Orchestrators** (Moses, Esther) run bus-based fleet orchestration scripts (`orch-bus-*`) and manage the update pipeline. **Server-agents** (Kustos, Gisu) run the full Hermes Cortex stack with inbox polling and bus health checks (`bus-*` scripts). **Dev-agents** (Titus, Joseph) run the agent message handler to process fleet commands via their bus inbox.

Agents communicate via a **PGMQ-based Agent Bus** with A2A (Agent-to-Agent) protocol — Postgres-backed message queues with auth, health monitoring, and fallover. No shared state, no race conditions.

### 🔒 Loop Governance — Enforced Change Discipline

Every code change follows a mandatory workflow that's **enforced at three levels**:

```
begin_change() → work → cycle_query() → feedback_accept() → end_change()
```

1. **🔴 MCP Enforcement** — The governance enforcer plugin blocks all write tools (`patch`, `write_file`, `terminal`) if no active lock exists
2. **⚡ Pre-Commit Hook** — Every `git commit` runs `score-cycle` against the diff, logs to the governance DB, and validates AGENTS.md integrity
3. **🕵️ Cron Auditor** — `governance-auditor` runs every 6h scanning for unscored changes + cleaning stale locks (>12h)

The **`pre-commit score hook`** auto-scores each commit. No `SKIP_SCORE=1` bypass — use `git commit --no-verify` for emergencies.

### 🤖 Auto-Remediation Pipeline

Issues fix themselves. The pipeline runs every 5 minutes:

```
remediation-sensor → remediation markers → agent-apply-fixes → agent-fixer
```

Sensors detect problems (crashed services, broken configs, stale locks), write remediation markers, and specialized fixer agents apply the cure — all autonomously.

### 🩺 Self-Healing Operations

**50 cron jobs** keep the system healthy without human intervention:

| Category | Crons | What |
|----------|-------|------|
| **Health** | `orch-fleet-watchdog`, `system-alert-watchdog`, `model-health-watchdog`, `bus-health-check` | Every 5-30 min health checks across all agents |
| **Recovery** | `service-recovery`, `agent-apply-fixes`, `remediation-sensor` | Auto-restart crashed services, apply fixes |
| **Governance** | `governance-auditor`, `scoring-activity-watchdog` | Score tracking, lock cleanup, audit trails |
| **Messaging** | `agent-bus-workday/evening/overnight` | Process agent-bus messages on schedule |
| **Sync** | `hermes-cortex-sync`, `memory-to-brain-sync`, `gbrain-update-sync` | Pull updates, persist memory, sync brain |
| **Security** | `threat-pipeline`, `agent-ip-submission` | Block threats, report IPs |
| **Maintenance** | `memory-pruning`, `session-cache-build`, `orch-skill-lifecycle` | Weekly consolidation, daily skill lifecycle pipeline |
| **Content** | `agent-daily-bible-reading`, `orch-skill-lifecycle`, `offline-code-index` | Daily spiritual, skill lifecycle (daily 04:00), code indexing |
| **Reports** | `orch-health-report`, `agent-gbrain-doctor` | Scheduled health briefings, brain quality |

All crons follow the **silent-when-good** pattern — zero output when healthy, targeted alerts on state changes.

### 🧠 Deep Knowledge Stack

A cascade retrieval system that works with or without internet:

```
Agent query → web_cache (50μs) → kiwix ZIM (localhost:8080) → gbrain (RAG) → LLM (always)
```

- **Web Cache** — Semantic search cache (sqlite-vec + Ollama embeddings, ~200MB LRU) — saves API costs
- **Offline Knowledge** — Wikipedia, WikiMed, Wikivoyage, Wikibooks available locally via Docker ZIM server
- **Offline Code Assistant** — 366 curated code snippets across 32 categories, 19 programming languages. `offline_code search` and `offline_code gen` work fully offline via Ollama. **Self-improving:** `offline_code learn` adds misses permanently.
- **Offline Reader** — Zero-dependency web UI (`python3 ops/offline/offline-reader.py`) for Bible (55+ languages), hymns, and wiki reference
- **gbrain** — Persistent knowledge brain (Postgres + pgvector, Docker) with automatic sync daemon

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
| Network | **pf firewall** | Default-deny, port-range rules, SSH rate-limiting |
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
| **Cortex Runtime** | `mcp-servers/`, `plugins/` | Hermes Agent bridge | MCP servers (`mcp-servers/`), governance enforcer plugin (`plugins/hermes-governance-enforcer/`) |
| **Cortex Ops** | `ops/` | Fleet operations | Installers (`ops/install/`), health scripts (`ops/scripts/health/`), watchdogs, offline stack, dashboard, agent-bus, web cache, cron infrastructure |

The boundary is directional: **Core ← Runtime ← Ops**. Core knows nothing about
Hermes Agent. Runtime translates Core contracts into Hermes-compatible hooks and
plugins. Ops uses both to keep the fleet running.

This model makes it possible to swap the agent runtime (e.g. to LangGraph or
Temporal) by replacing only the Runtime Adapter layer.

Detailed breakdown: [`docs/architecture.md`](docs/architecture.md#code-architecture--three-layer-model)

### 🧩 Optional Profiles

The repo ships with a neutral enterprise core. Personal or opinionated content
lives in `profiles/` as optional layers:

| Profile | Contents |
|---------|----------|
| `personal/` | Bible reading skill, soul-refinement workflow, agent SOUL profiles (Moses, Esther, Titus, Kustos, Gisu) |

All paths from personal profiles are symlinked from their canonical locations for
backward compatibility. To exclude a profile, remove the symlink and the profile
directory won't be shipped.

See [`profiles/README.md`](profiles/README.md).

---

## 🚀 One-Command Install

> **🔒 Before installing:** Read the [Security Guide](docs/SECURITY.md).

### 🐧 New Linux Server — Full Bootstrap

Bare Ubuntu 24.04 VM? This single command does everything: installs Docker, Ollama, Hermes CLI, clones the repo, configures secrets, sets up nginx + Let's Encrypt SSL, hardens UFW and fail2ban, and verifies the stack.

```bash
# One-liner — no clone needed
curl -fsSL https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/deploy/bootstrap.sh | bash
```

Expects: **Fresh Ubuntu 24.04 LTS** with SSH access. Interactive prompts for API keys and domain.
Takes: **8–15 minutes** (mostly model downloads).

> ⚠️ This is a *server bootstrap* — it installs Docker, nginx, Langfuse.
> For a laptop/client install, use `install.sh` below.

### 🖥️ Existing Machine — install.sh (macOS, Linux, WSL)

**Quick start (30 seconds):** Try the governance scoring tools:

```bash
bash core/governance/setup.sh    # install deps + symlinks
score-cycle --help                    # ready to use
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
curl -fsSL https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/install/install.sh | bash

# Or clone for offline install / inspection:
git clone --depth 1 https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex
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
| 1 | **Ollama** | Native installer per OS; bound to localhost |
| 2 | **Bun** | JavaScript runtime for gbrain |
| 3 | **gbrain** | Persistent knowledge brain (Postgres + pgvector via Docker) |
| 4 | **Brain dirs** | `~/brain/{default,…}` with MECE directory schema + .gitignore + git init |
| 5 | **gbrain sync** | Launchd/systemd daemon — syncs brain every 2 minutes |
| 6 | **Observability** † | Langfuse + Cortex Dashboard |
| 7 | **`/brain` plugin** | Hermes slash command for gbrain queries |
| 8 | **Scripts** | 199+ scripts: health checks, watchdogs, sync, governance, security |
| 9 | **Plugin enable** | Auto-activates in Hermes config |
| 10 | **Skills** | 8+ shared skills installed to `~/.hermes/skills/` |
| 11 | **Web Cache** | Semantic web result cache (sqlite-vec + Ollama) |
| 12 | **Offline Knowledge** | Cascade tool + kiwix ZIM Docker + prep scripts |
| 13 | **Offline Reader** | `python3 ops/offline/offline-reader.py` — zero-dependency web UI |
| 14 | **Code Corpus** | 366 snippets across 32 categories, 19 languages; RAG index via Ollama |
| 15 | **Auto-Update** | `auto-update.sh` — silent cron-based content updater |
| 16 | **Cron Jobs** | 50 maintenance crons: health, security, sync, recovery, reporting |
| 17 | **nginx** † | Reverse proxy for Langfuse + Dashboard + hardening |
| | *† Server profile only* | |

### Configuration

```bash
export CORTEX_OS="linux"                     # Auto-detected: darwin, linux, windows
export CORTEX_PROFILE="laptop"               # 'server' (default) or 'laptop'
export CORTEX_SOURCES="me,shared,default"    # Brain source names
export CORTEX_HOME="$HOME"                   # User home directory
export HERMES_HOME="$HOME/.hermes"           # Hermes config directory
```

**OS Support:** macOS (launchd, Homebrew) · Linux (systemd, apt/dnf/pacman) · Windows (winget/choco, limited)

**Profiles:** `server` (full stack, Docker) · `laptop` (lean, no Docker — ideal for mobile)

### Multi-Person Setup

```bash
export CORTEX_SOURCES="luke,amy,shared,default"
bash ~/hermes-cortex/ops/install/install.sh
```

Each source has isolated memory and .gitignore. The `/brain` slash command adapts to whatever sources you configure.

---

## 🔄 Upgrading

To upgrade an existing Hermes Cortex installation:

```bash
cd ~/hermes-cortex
git pull --ff-only
bash ops/scripts/cortex-update.sh          # delta update (changed files only)
```

The `cortex-update.sh` script auto-detects what files changed and deploys only the deltas. For a full re-deployment:

```bash
bash ops/scripts/cortex-update.sh --force-all
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
Gisu   ──UPDATE_RESULT──→ AgentBus ──→ Moses
Titus  ──UPDATE_RESULT──→ AgentBus ──→ Moses
```

### Script Naming Convention

| Prefix | Scope | Location | Examples |
|--------|-------|----------|---------|
| `orch-bus-*` | Orchestrator-only (Moses, Esther) — run from repo | `ops/scripts/orch-bus/` | `orch-bus-fleet-dispatch`, `orch-bus-fleet-rollback` |
| `bus-*` | Fleet-wide — deployed to all agents | `ops/scripts/orch-bus/` (registered via `cortex-update.sh`) | `bus-sensor`, `bus-health-check`, `bus-readiness-check` |
| `agent-message-handler` | Agent-side inbox handler | `ops/scripts/agent/` | Polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK |
| `agent-*` | General agent crons | `ops/scripts/agent/` | `agent-inbox-poll` |

### Update Flow

1. **Pre-flight:** `bus-readiness-check.py` verifies bus health, git state, and agent inbox queues
2. **Dispatch:** `orch-bus-fleet-dispatch.py` sends `UPDATE_REQUEST` to each server-agent's inbox
3. **Server-agents** poll their inbox, run `cortex-update.sh`, post `UPDATE_RESULT` back
4. **Dev-agents**: `agent-message-handler` polls their inbox, runs `cortex-update`, posts `UPDATE_RESULT`
5. **Rollback:** `orch-bus-fleet-rollback.py` reads dispatch state and sends `ROLLBACK_REQUEST` to failed agents
6. **Auth check:** `bus-git-auth-check.py` verifies each agent can pull from the remote

### Shared Bus Library

All fleet scripts use `ops/scripts/lib/cortex_bus.py` — a shared HTTP API wrapper that reads `CORTEX_BUS_URL` / `CORTEX_BUS_FALLBACK_URL` from the environment. This eliminates the old pattern of `docker exec` calls into the Postgres container.

### Push-Agent Install

For dev-agents (macOS, partial stack): `ops/install/install-push-agent.sh` installs the update handler as a service without Docker, nginx, or gbrain.

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
| `ops/scripts/install-crons.sh` | Install/remove all 50 maintenance cron jobs |
| `ops/scripts/manage/hermes-update.sh` | Silent nightly update of Hermes Agent |
| `ops/scripts/manage/hermes-cortex-sync.sh` | Nightly git pull of hermes-cortex repo |
| `ops/scripts/manage/nginx-threat-pipeline.sh` | Daily nginx log scan + auto-ban repeat attackers |
| `ops/scripts/manage/deploy-blocked-ips.sh` | Deploy shared blocklist across fleet |
| `ops/scripts/manage/analyze-failures.py` | Analyze cron failure patterns |
| `ops/scripts/manage/template-diff-check.py` | Detect template drift across agents |

---

## 📚 Documentation

| Document | What it covers |
|----------|---------------|
| [Security Guide](docs/SECURITY.md) | 🔒 Port risks, file permissions, firewall setup, recovery |
| [Architecture](docs/architecture.md) | System diagram, services, port map, design principles |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |
| [Loop Governance Reference](docs/loop-governance-reference.md) | Full governance workflow, scoring, enforcement layers |
| [Fleet Reference](docs/fleet-reference.md) | Agent summary, cron table, auto-remediation pipeline |
| [Setup Reference](docs/setup-reference.md) | Ollama config, env vars, cron tiers, model selection |
| [Pipeline Reference](docs/pipeline-reference.md) | Lessons, sessions, skills, memory, quality pipeline |
| [Operations Reference](docs/operations-reference.md) | Inbox architecture, offline code, rules engine |
| [Computer Specs](docs/computer-specs.md) | Hardware recommendations by RAM tier |
| [Offline Scenarios](docs/offline-travel-stack.md) | Using Hermes without internet |
| [AGENTS.md](AGENTS.md) | Agent execution contract, loop governance, inbox framework |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute to hermes-cortex |

---

> *"The more we get to know about our universe, the more the hypothesis that there is a Creator God, who designed the universe for a purpose, gains in credibility as the best explanation of why we are here."* — John Lennox

---

*Built by [@fleet-operator](https://github.com/fleet-operator) · Powered by 🦞 [Hermes Agent](https://hermes-agent.nousresearch.com) · Version `v2.0.0` · [MIT License](LICENSE) · See [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) for component attributions*
