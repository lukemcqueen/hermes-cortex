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
┌──────────────┐  ┌──────────────────┐  ┌────────────┐  ┌──────────────┐
│   Langfuse   │  │  Cortex Dashboard│  │  Web Cache │  │   GBrain     │
│  (LLM Obs.)  │  │   (Flask + JS)   │  │ (sqlite-vec│  │ (Knowledge)  │
│ local:3000   │  │  local:8901      │  │  + Ollama) │  │ PGLite       │
│ ext:13002    │  │  ext:13001       │  │  ~200MB    │  │ 4 sources    │
└──────────────┘  └──────────────────┘  └────────────┘  └──────────────┘
       │                   │                    │              │
       ▼                   ▼                    ▼              ▼
┌──────────────────────────────────────────────────────────────────────┐
│              nginx Reverse Proxy (macOS Host)                        │
│  :13001 → Cortex Dashboard (port 8901, HTTPS)                       │
│  :13002 → Langfuse (port 3000, HTTPS)                               │
│  :13003 → Health Server (port 8905, HTTPS)                           │
│  TLS + Basic Auth on all external ports, rate-limited               │
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

## Layers

| Layer | Tool | Purpose |
|-------|------|---------|
| **Agent** | Hermes Agent | Self-improving runtime with learning loop, subagents, cron, Telegram interface |
| **Observability** | Langfuse + Cortex Dashboard | Trace inspection, session replay, LLM evaluation scoring, system health monitoring |
| **Cache** | Web Cache (sqlite-vec) | Local semantic cache for web_search results. Cuts API costs, enables offline fallback |
| **Memory** | GBrain | Long-term knowledge graph via Markdown files across 4 sources (luke, amy, shared, default). PGLite engine with Ollama embeddings. Sync daemon + dream cycle |
| **Offline** | kiwix ZIM + Code Corpus | Zero-internet operation: medical, travel, education, language, code generation. All local |
| **Config** | GitHub (two-repo system) | Public repo: installer, skeleton, docs. Private repo: full config, scripts, dashboard, nginx config. Brain content on private branches |

## Repository Architecture

| Repo | Visibility | Contents |
|------|-----------|----------|
| `hermes-cortex` | **Public** | Installer (`install.sh`), skeleton config, architecture docs, skills (8), offline content, bump-version script. No secrets or brain data |
| `hermes-cortex-private` | **Private** | Full system config (`config.yaml`), dashboard (Flask + JS), nginx config, 13 utility scripts, all cron setups |
| `brain-*` branches on private repo | **Private** | Brain content on `brain-luke`, `brain-amy`, `brain-shared`, `brain-default` branches. Each is a clean single-commit orphan branch synced via gbrain |

## Services

| Service | Port | Purpose | Stack |
|---------|------|---------|-------|
| Ollama | 11434 | Local LLM serving (localhost-only) | Native macOS, launchd-managed |
| Hermes Gateway | — | Agent runtime | Python, gateway.run, launchd |
| Langfuse | 3000 | LLM trace observability | Node.js standalone, launchd |
| Cortex Dashboard | 8901 | System + Langfuse companion | Flask + pure JS/HTML |
| Health Server | 8905 | System health endpoint | Flask, launchd |
| Agent Inbox | **8903 (localhost-only)** | Inter-agent messaging — **MCP-only access via inbox_send/inbox_read/inbox_watch tools**. Internal FastAPI backend for inbox-mcp.py, no external endpoint |
|| nginx | 13001–13003 | Reverse proxy for all services | Homebrew, launchd |
| MinIO | 9002 (S3 API), 9001 (console) | S3-compatible blob storage | Native binary, launchd |
| ClickHouse | 8123 (HTTP), 9000 (native) | OLAP database for Langfuse traces | Native binary |
| PostgreSQL 16 | 5432 | Primary database | Native, launchd |
| Redis | 6379 | Queue broker for Langfuse | Native, launchd |
| kiwix-serve | 8080 | ZIM content server (offline) | Docker, launchd |
| Offline Reader | 8081 | Bible/hymns/reference browser | stdlib Python |
| GBrain Sync | — | Memory sync daemon | Bun, PGLite, launchd (2min interval) |

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
| 13003 | Health Server (HTTPS) | Yes (Basic Auth) | Strict rate-limit 6r/m, conn-limit 5/IP |

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

**See also:** [Security Guide → `docs/SECURITY.md`](./SECURITY.md) | [Troubleshooting → `docs/troubleshooting.md`](./troubleshooting.md)
