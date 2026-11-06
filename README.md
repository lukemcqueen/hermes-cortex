# 🧠 Steadfaste Fleet

> *A self-contained multi-agent fleet platform — installer, skill set, orchestration, enforced governance, self-healing operations, and an offline knowledge stack. Runs on your own hardware, with or without Hermes.*

**Version: 2.0.0** · [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) · [![GitHub](https://img.shields.io/github/license/lukemcqueen/steadfaste-fleet)](LICENSE) · [![Docs](https://img.shields.io/badge/Docs-docs%2F-444444)](docs/)

<div align="center">
  <img src="docs/assets/steadfaste-logo.svg" alt="Steadfaste" width="320"/>
</div>

**Steadfaste Fleet** is a self-contained installer, public skill set, and multi-agent platform. It ships a **governance engine** that enforces change discipline at the tool level, a **self-healing operations system**, an **agent-to-agent messaging bus**, and a **deep offline knowledge stack** — all running on your own hardware with zero cloud dependency.

> **Runtime:** the reference runtime is [Hermes Agent](https://hermes-agent.nousresearch.com). The shipped Runtime adapter layer (`mcp-servers/` + `plugins/`) targets Hermes today, but the platform is designed to be runtime-swappable — `core/` has zero runtime dependency, so switching runtime means replacing that one adapter layer, not the platform.

---

## 🏗️ Architecture

The repository is organized into three layers, separating contracts from runtime integration from operations:

| Layer | Directory | Purpose | Contents |
|-------|-----------|---------|----------|
| **Core** | `core/` | Schemas, governance, identity | Canonical type definitions, loop-governance engine, agent-identity contracts — zero runtime dependency |
| **Runtime** | `mcp-servers/`, `plugins/` | Runtime adapter | MCP servers (`mcp-servers/`) and the governance-enforcer plugin (`plugins/governance-enforcer/`) — Hermes-shaped today, swappable |
| **Ops** | `ops/` | Fleet operations | Installers (`ops/install/`), health scripts, watchdogs, offline stack, dashboard, agent bus, web cache, cron infrastructure |

The boundary is directional: **Core ← Runtime ← Ops**. Core knows nothing about the runtime; Runtime translates Core contracts into runtime-compatible hooks and plugins; Ops uses both to keep the fleet running. Swapping the runtime (e.g. to another agent harness) means replacing only the Runtime adapter.

Detailed breakdown: [`docs/architecture.md`](docs/architecture.md)

---

## 🤖 Fleet Agents (Illustrative)

The platform runs a coordinated team of specialized agents. These names are the operator's fleet; yours will differ — the repo is a framework others deploy with their own agent names.

| Agent | Role | Responsibility |
|-------|------|---------------|
| **Moses** 🗂️ | Orchestrator | Fleet health, cron management, infrastructure, governance |
| **Esther** 👑 | Backup Orchestrator | Cover for Moses during downtime |
| **Titus** 🏗️ | DevOps Engineer | Fleet tooling, service health, recovery automation |
| **Joseph** ⚙️ | Server Agent | Full-stack infra: nginx, services, web ops, fleet updates |
| **Kustos** 🛡️ | Security | Threat detection, blocklist management, access control |
| **Gisu** 💬 | Communications | Inbox routing, message triage, cross-agent coordination |

Agents communicate via a **PGMQ-based Agent Bus** with an A2A protocol — Postgres-backed message queues with auth, health monitoring, and failover. No shared state, no race conditions.

---

## 🔒 Enforced Governance

Every code change follows a mandatory workflow, **enforced at four levels**:

```
begin_change() → work → cycle_query() → feedback_accept() → end_change() → push
```

1. **🔴 Enforcer plugin** — blocks all write tools (`patch`, `write_file`, `terminal`) if no active governance lock exists
2. **⚡ Pre-commit hook** — every `git commit` scores the diff, logs to the governance DB, and runs adversarial verification
3. **🕵️ Cron auditor** — runs every 6h scanning for unscored changes and cleaning stale locks
4. **🚀 Pre-push gates** — governance lock, review receipt, syntax, doc coverage, pull-before-push

See [Loop Governance Reference](docs/loop-governance-reference.md) · [Review Receipt Gate](docs/review-receipt-gate.md).

### 🤖 Self-Healing Operations

Issues fix themselves. The remediation pipeline runs every 5 minutes:

```
remediation-sensor → remediation markers → agent-remediate-apply → agent-fixer
```

Sensors detect problems (crashed services, broken configs, stale locks), write markers, and fixer agents apply the cure autonomously. ~70 cron jobs shipped across the installers keep the system healthy — all following a **silent-when-good** pattern: zero output when healthy, targeted alerts on state changes.

---

## 🎁 What You Can Take From This Repo

This is a working enterprise-grade agentic harness, not just a skill pack. Each pattern is implemented in real code with exact file paths:

| Take-away | Where | What you get |
|-----------|-------|--------------|
| 🛡️ **Bad-actor IP blocklist** | [`ops/install/deploy/nginx/blocked_ips.add`](ops/install/deploy/nginx/blocked_ips.add) | 14,000+ evidence-based blocked IPs, one per line — drop into nginx/fail2ban/UFW today |
| 🤝 **Agent-to-agent messaging** | [`ops/scripts/lib/fleet_bus.py`](ops/scripts/lib/fleet_bus.py) | Production A2A over Postgres PGMQ — `bus_send`/`bus_read`/`bus_archive`, correlation IDs, no Kafka/Redis |
| 💰 **RAG + semantic caching** | [`ops/web-cache/web_cache.py`](ops/web-cache/web_cache.py) | sqlite-vec + Ollama cache that answers queries **before** the LLM — cuts token spend, works offline |
| 🔒 **Enforced change governance** | [`plugins/governance-enforcer/`](plugins/governance-enforcer/) | Change discipline **blocked at the tool level**, not suggested |
| 🤖 **Self-healing operations** | [`ops/scripts/health/agent-remediation-sensor.py`](ops/scripts/health/agent-remediation-sensor.py) | sensor → marker → fixer pipeline that repairs crashes before you wake up |
| 🕵️ **Threat pipeline** | [`ops/scripts/manage/agent-nginx-threat-pipeline.sh`](ops/scripts/manage/agent-nginx-threat-pipeline.sh) | Daily log scan → fail2ban bans → new blocklist entries, evidence-based |

👉 **Full patterns guide with reading order:** [`docs/PATTERNS.md`](docs/PATTERNS.md)

---

## 🚀 Install

> **🔒 Before installing:** Read the [Security Guide](docs/SECURITY.md).

### 🐧 New Linux Server — Full Bootstrap

Bare Ubuntu 24.04 VM? This single command installs Docker, Ollama, Hermes CLI, clones the repo, configures secrets, sets up nginx + Let's Encrypt SSL, hardens UFW and fail2ban, and verifies the stack.

```bash
# One-liner — no clone needed
curl -fsSL https://raw.githubusercontent.com/lukemcqueen/steadfaste-fleet/main/ops/deploy/bootstrap.sh | bash
```

Expects: **Fresh Ubuntu 24.04 LTS** with SSH access. Interactive prompts for API keys and domain.
Takes: **8–15 minutes** (mostly model downloads).

### 🖥️ Existing Machine — install.sh (macOS, Linux, WSL)

```bash
# One-liner — no clone needed
curl -fsSL https://raw.githubusercontent.com/lukemcqueen/steadfaste-fleet/main/ops/install/install.sh | bash

# Or clone for offline install / inspection:
git clone --depth 1 https://github.com/lukemcqueen/steadfaste-fleet.git ~/steadfaste-fleet
bash ~/steadfaste-fleet/ops/install/install.sh

# Check prerequisites only:
bash ~/steadfaste-fleet/ops/install/install.sh --check

# macOS — Laptop profile: lean, no Docker
CORTEX_PROFILE=laptop bash ~/steadfaste-fleet/ops/install/install.sh

# Linux — auto-detects systemd, apt/dnf/pacman
CORTEX_OS=linux bash ~/steadfaste-fleet/ops/install/install.sh
```

`install.sh` installs: Ollama (localhost-bound), the mycortex knowledge brain (git-in → shared Postgres index), the web cache, ~390 shared skills, scoring hooks + MCP servers, the offline stack, and — server profile only — Langfuse + the dashboard behind nginx with hardening.

**Configuration:**

```bash
export CORTEX_OS="linux"                # Auto-detected: darwin, linux, windows
export CORTEX_PROFILE="laptop"          # 'server' (default) or 'laptop'
export CORTEX_SOURCES="me,shared,default"  # Brain source names
export CORTEX_HOME="$HOME"              # User home directory
```

**OS support:** macOS (launchd, Homebrew) · Linux (systemd, apt/dnf/pacman) · Windows (winget/choco, limited)
**Profiles:** `server` (full stack, Docker) · `laptop` (lean, no Docker)

---

## 🔄 Upgrading

```bash
cd ~/steadfaste-fleet
git pull --ff-only
bash ops/scripts/fleet-update.sh     # delta update (changed files only)
```

`fleet-update.sh` auto-detects changed files and deploys only the deltas. After a major version upgrade, agents should `/reset` their sessions to pick up new skills and plugin configurations.

---

## 🚚 Fleet Update Pipeline

The fleet update pipeline orchestrates coordinated rollouts across all agents using the Agent Bus. Pre-flight checks verify bus health and git state; orchestrators dispatch `UPDATE_REQUEST` to each agent's inbox; agents poll, run `fleet-update.sh`, and post `UPDATE_RESULT` back; a rollback script re-dispatches `ROLLBACK_REQUEST` to failed agents. All fleet scripts use the shared `ops/scripts/lib/cortex_bus.py` library.

---

## 🧠 Offline Knowledge Stack

A cascade retrieval system that works with or without internet:

```
Agent query → web_cache → kiwix ZIM (localhost:8080) → mycortex (RAG) → LLM
```

- **Web Cache** — semantic search cache (sqlite-vec + Ollama embeddings) — saves API costs
- **Offline Knowledge** — Wikipedia, WikiMed, Wikivoyage, Wikibooks available locally via a Docker ZIM server
- **Offline Code Assistant** — 540+ curated code snippets across 30+ languages; `offline_code search`/`gen` work fully offline via Ollama, `offline_code learn` adds misses permanently
- **Offline Reader** — zero-dependency web UI (`python3 ops/offline/offline-reader.py`) for Bible (55+ languages), hymns, and wiki reference
- **mycortex** — git repos as source of truth → shared Postgres index (FTS + pg_texample + pgvector), fail-closed RLS per profile, no daemon. [Design doc](docs/design/mycortex-DESIGN.md)

| Scenario | `prep-offline` mode | Content | Size |
|----------|---------------------|---------|------|
| 🌴 **Jungle Travel** | `--mode=travel` | WikiMed + Wikivoyage + Simple Wiki + Wiktionary | ~6 GB |
| 🏗️ **Offline Dev** | `--mode=build` | Simple Wiki + Wikibooks + Wiktionary | ~7 GB |
| 📚 **Kid Learning** | `--mode=education` | Simple Wiki + Wikibooks + Wikivoyage | ~5 GB |

```bash
prep-offline --mode=travel
offline_knowledge stats
offline_knowledge query "symptoms of malaria"
```

---

## 🔧 Key Scripts

| Script | Purpose |
|--------|---------|
| `ops/install/install.sh` | **Main installer** |
| `ops/scripts/fleet-update.sh` | Deploy scripts from repo — run after every `git pull` |
| `ops/scripts/manage/fleet-doctor.py` | System diagnostics, fix common issues |
| `ops/scripts/install/install-score-hook.sh` | Install/remove pre-commit scoring hooks |
| `ops/scripts/install-crons.sh` | Install/remove agent cron jobs |
| `ops/scripts/manage/agent-nginx-threat-pipeline.sh` | Daily nginx log scan + auto-ban repeat attackers |
| `ops/scripts/manage/deploy-blocked-ips.sh` | Deploy shared blocklist across fleet |
| `ops/scripts/lib/fleet_bus.py` | Shared Agent Bus HTTP API wrapper |

---

## 📚 Documentation

| Document | What it covers |
|----------|---------------|
| [Enterprise Patterns](docs/PATTERNS.md) | 🎁 **Start here** — reusable take-aways with file paths and reading order |
| [Security Guide](docs/SECURITY.md) | 🔒 Port risks, file permissions, firewall setup, recovery |
| [Architecture](docs/architecture.md) | System diagram, services, port map, design principles |
| [Loop Governance Reference](docs/loop-governance-reference.md) | Full governance workflow, scoring, enforcement layers |
| [Review Receipt Gate](docs/review-receipt-gate.md) | 🚀 Why review must precede push, how to satisfy the gate |
| [Fleet Reference](docs/fleet-reference.md) | Agent summary, cron table, auto-remediation pipeline |
| [Setup Reference](docs/setup-reference.md) | Ollama config, env vars, cron tiers, model selection |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |
| [AGENTS.md](AGENTS.md) | Agent execution contract, loop governance, inbox framework |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

> The public repo carries framework docs only; internal decision records and host-specific implementation docs live in a separate private repo.

---

> *"The more we get to know about our universe, the more the hypothesis that there is a Creator God, who designed the universe for a purpose, gains in credibility as the best explanation of why we are here."* — John Lennox

---

*Version `v2.0.0` · [MIT License](LICENSE) · See [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) for component attributions*