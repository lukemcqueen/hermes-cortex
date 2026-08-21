# 🏗️ Hermes Cortex Architecture

## Overview

```
  You (Telegram / CLI)
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                  Hermes Agent (Runtime)                       │
│  • Tools & Skills  • Cron Jobs  • Memory  • Subagents        │
└──────┬──────────────────────────────────┬────────────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────┐  ┌──────────────────┐  ┌────────────┐  ┌──────────────┐  ┌────────────────┐
│   Langfuse   │  │  Cortex Dashboard│  │  Web Cache │  │   Mycortex     │  │  Agent Bus     │
│  (LLM Obs.)  │  │   (Flask + JS)   │  │ (sqlite-vec│  │ (Knowledge)  │  │  (PGMQ Queue)  │
│ local:3000   │  │  local:8901      │  │  + Ollama) │  │ local:15432  │  │ local:8903     │
│ ext:13002    │  │  ext:13001       │  │  ~200MB    │  │  pgvector)  │  │ ext:13004     │
│              │  │                   │  │            │  │ bus queues  │  │ (waiting)     │
└──────────────┘  └──────────────────┘  └────────────┘  └──────┬───────┘  └────────────────┘
       │                   │                    │              │                │
       ▼                   ▼                    ▼              ▼                ▼
┌──────────────────────────────────────────────────────────────────────┐
│              nginx Reverse Proxy (macOS Host)                        │
│  :13001 → Cortex Dashboard (port 8901, HTTPS)                       │
│  :13002 → Langfuse (port 3000, HTTPS)                               │
│  :13004 → Agent Bus (port 8903, HTTPS) — PGMQ message queue         │
│  :13007 → Health Server (port 8905, HTTPS)                         │
└──────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Offline Knowledge Layer                           │
│  kiwix-serve (Docker, :8080) · prep-bible · prep-hymns              │
│  386 code snippets (26 langs) · offline-reader (:8081)              │
│  ZIM content: WikiMed, Wikivoyage, Simple Wiki, Wiktionary          │
└──────────────────────────────────────────────────────────────────────┘
```

## Code Architecture — Three-Layer Model

The repository is organized into three distinct layers, each with a well-defined boundary:

```
┌────────────────────────────────────────────────────────────────┐
│                    CORTEX CORE                                  │
│  Canonical schemas, workflow state, policy, identity.          │
│  Zero runtime dependency — types and contracts only.           │
│                                                                │
│  core/governance/    — Loop governance DB, scorer, feedback    │
│  core/schemas/       — WorkflowRun, Policy, KnowledgeRecord    │
│  core/identity/      — Agent identity contracts                │
├────────────────────────────────────────────────────────────────┤
│                    CORTEX RUNTIME ADAPTER                       │
│  Hermes Agent integration — plugins, MCPs, hooks, skills.     │
│  Thin bridge: policies from Core → enforcement in Runtime.     │
│                                                                │
│  plugins/hermes-     — Governance enforcer plugin, git hooks   │
│  mcp-servers/— Inbox & governance MCP servers          │
│  skills/              — Hermes skill definitions                │
├────────────────────────────────────────────────────────────────┤
│                    CORTEX OPERATIONS                            │
│  Installers, monitors, services, offline stack, fleet mgmt.   │
│  Self-healing, silent-when-good, offline-first.                │
│                                                                │
│  ops/install/        — install.sh, deploy/, nginx configs      │
│  ops/scripts/        — Health, inbox, archive, agent scripts   │
│  ops/services/       — Dashboard, agent-inbox, cortex-bus, A2A  │
│  ops/offline/        — Kiwix, code corpus, offline reader      │
│  ops/web-cache/      — SQLite-vec semantic cache               │
└────────────────────────────────────────────────────────────────┘
```

This separation lets each layer evolve independently. For example, swapping the
Hermes Agent runtime for LangGraph or Temporal means replacing the Runtime
Adapter layer — the Core schemas and Ops infrastructure stay unchanged.

---

## Layers (Deployment)

| Layer | Tool | Purpose |
|-------|------|---------|
| **Agent** | Hermes Agent | Self-improving runtime with learning loop, subagents, cron, Telegram interface |
| **Observability** | Langfuse + Cortex Dashboard | Trace inspection, session replay, LLM evaluation scoring, system health monitoring |
| **Cache** | Web Cache (sqlite-vec) | Local semantic cache for web_search results. Cuts API costs, enables offline fallback |
|| **Memory** | Mycortex | Long-term knowledge graph via Markdown files across 4 sources (luke, amy, shared, default). **Postgres + pgvector** engine with Ollama embeddings. Sync daemon. Queryable by any agent via `:15432` |
| **Offline** | kiwix ZIM + Code Corpus | Zero-internet operation: medical, travel, education, language, code generation. All local |
| **Config** | GitHub (two-repo system) | Public repo: installer, skeleton, docs. Private repo: full config, scripts, dashboard, nginx config. Brain content on private branches |

## Repository Architecture

| Repo | Visibility | Contents |
|------|-----------|----------|
| `hermes-cortex` | **Public** | Installer (`install.sh`), skeleton config, architecture docs, skills (8), offline content, bump-version script. No secrets or brain data |
| `private-data` | **Local** | Full system config (`config.yaml`), dashboard (Flask + JS), nginx config, 13 utility scripts, all cron setups |
| `brain-*` branches on private repo | **Private** | Brain content on `brain-luke`, `brain-amy`, `brain-shared`, `brain-default` branches. Each is a clean single-commit orphan branch synced via mycortex |

## Services

| Service | Port | Purpose | Stack |
|---------|------|---------|-------|
| Ollama | 11434 | Local LLM serving (localhost-only) | Native macOS, launchd-managed |
| Hermes Gateway | — | Agent runtime | Python, gateway.run, launchd |
| Langfuse | 3000 | LLM trace observability | Node.js standalone, launchd |
| Cortex Dashboard | 8901 | System + Langfuse companion | Flask + pure JS/HTML |
| Health Server | 8905 | System health endpoint | Flask, launchd |
| Agent Bus | **8903** | Agent Bus (PGMQ) — inter-agent messaging. Health endpoint, web dashboard, pub/sub REST API. nginx proxy on port 13004 with `auth_basic` | FastAPI + Postgres PGMQ |
|| nginx | 13001–13007 | Reverse proxy for all services | Homebrew, launchd |
| MinIO | 9002 (S3 API), 9001 (console) | S3-compatible blob storage | Native binary, launchd |
| ClickHouse | 8123 (HTTP), 9000 (native) | OLAP database for Langfuse traces | Native binary |
| PostgreSQL 16 | 5432 | Primary database | Native, launchd |
| Redis | 6379 | Queue broker for Langfuse | Native, launchd |
| kiwix-serve | 8080 | ZIM content server (offline) | Docker, launchd |
| Offline Reader | 8081 | Bible/hymns/reference browser | stdlib Python |
|| Mycortex Postgres | 15432 | Knowledge brain database (pgvector) | Docker, compose-managed in langfuse stack |
| Legacy Sync | — | Memory sync daemon (Docker Postgres + pgvector) | Bun, **systemd (user service)** — auto-starts on boot |

## External Access

All external services are accessed via nginx on custom ports with TLS + basic auth,
rate-limited by nginx + fail2ban (4 jails, ban escalation 1h→4wk):

> **Per-agent port ranges (Luke's deployment):** The `13xxx` ports below are the
> default convention. Individual agents use different ranges to allow multiple
> agent servers on the same domain — **Moses** uses `13xxx`, **Joseph** uses
> `12xxx`, **Esther** uses `14xxx`. Each agent's nginx config maps their own
> services to their own range.

| Port | Service | Auth Required | Notes |
|------|---------|--------------|-------|
| 13001 | Cortex Dashboard (HTTPS) | Yes (Basic Auth) | nginx rate-limit 20/5r/s + conn-limit 10/IP |
| 13002 | Langfuse (HTTPS) | Yes (Basic Auth) | nginx rate-limit + _next/static excluded from auth limiter |
| 13007 | Health Server | **No auth** (health endpoint, Moses polls this) | Strict rate-limit 6r/m, conn-limit 5/IP |

## Security Stack

| Layer | Tool | What it does |
|-------|------|-------------|
| Application | nginx rate limiting | 20 req/5s per IP, max 10 concurrent connections per IP |
| Firewall | pf (packet filter) | Default-deny, port-range rules (22, 990, 13001-13099), SSH rate limit (5/60s) |
| Auto-ban | fail2ban (4 jails) | nginx-http-auth, nginx-limit-req, nginx-botsearch, nginx-bad-request |
| Network | macOS app firewall | Stealth mode, blocks incoming by default |

## Design Principles

1. **Thin harness, fat skills** — The agent framework stays lean; the value lives in well-crafted skills and memory
2. **Visibility first** — Every agent action is observable via Langfuse traces + evaluation scores
3. **Persistence by design** — Config, skills, memory, and brain content are all version-controlled
4. **Offline-first** — Cache + ZIM + code corpus work identically with or without internet
5. **Separation of concerns** — Public (installer/docs) ≠ Private (config/scripts) ≠ Brain (content on branches)
6. **No PII in public** — Both repos surgically scrubbed via git-filter-repo; brain data only on private branches

---

## Mycortex Autopilot — Systemd Service

The legacy autopilot runs as a **user-level systemd service** on Linux (not launchd — that's macOS legacy in the table). This means it:

- ✅ **Survives reboots** — auto-starts when the machine boots (linger enabled for user `moses`)
- ✅ **Auto-restarts on crash** — `Restart=always`, `RestartSec=30`, `StartLimitBurst=10` per 5 min
- ✅ **Carries API keys** — wrapper script sources `~/.zshenv` / `~/.zshrc` so secrets reach autopilot

### Management

```bash
# Check status
systemctl --user status legacy-autopilot.service

# View recent logs
journalctl --user -u legacy-autopilot.service -n 50

# Restart
systemctl --user restart legacy-autopilot.service

# Follow live
journalctl --user -u legacy-autopilot.service -f
```

### Running mycortex Commands

With Postgres, `mycortex query` and other CLI commands work **while the sync daemon is running** — no lock contention. Unlike PGLite, the Postgres engine supports concurrent connections.

See [`docs/legacy Postgres-migration.md`](legacy Postgres-migration.md) for setup and [`docs/mycortex-pglite-recovery.md`](mycortex-pglite-recovery.md) for legacy rollback.

### Initial Setup (fresh install)

```bash
# Install mycortex first
bun install -g github:garrytan/mycortex

# Create the service
legacy autopilot --install

# Enable linger (one-time, needs sudo)
sudo loginctl enable-linger moses
```

The service file lives at `~/.config/systemd/user/legacy-autopilot.service` and the wrapper at `~/.legacy-brain/autopilot-run.sh`. Both are auto-generated by `legacy autopilot --install`.

**See also:** [Security Guide → `docs/SECURITY.md`](./SECURITY.md) | [Troubleshooting → `docs/troubleshooting.md`](./troubleshooting.md)
