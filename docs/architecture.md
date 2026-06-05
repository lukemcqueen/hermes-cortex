# 🏗️ Hermes Cortex Architecture

## Overview

```
  You (Telegram / CLI)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                  Hermes Agent (Runtime)               │
│  • Tools & Skills  • Cron Jobs  • Memory  • Subagents │
└──────┬──────────────────────────────────┬────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   Langfuse   │  │  Cortex Dashboard│  │   GBrain     │
│  (LLM Obs.)  │  │   (Flask + JS)   │  │ (Knowledge)  │
│ local:3001   │  │  local:8901      │  │ PGLite       │
│ ext:13002    │  │  ext:13001       │  │ 4 sources    │
└──────────────┘  └──────────────────┘  └──────────────┘
       │                   │                    │
       ▼                   ▼                    ▼
┌──────────────────────────────────────────────────────┐
│           nginx Reverse Proxy (macOS Host)            │
│  :13002 → Langfuse (LLM observability, port 3001)     │
│  :13001 → Cortex Dashboard (companion, port 8901)     │
│  TLS + Basic Auth on all external ports               │
└──────────────────────────────────────────────────────┘
```

## Layers

| Layer | Tool | Purpose |
|-------|------|---------|
| **Agent** | Hermes Agent | Self-improving runtime with learning loop, subagents, cron, Telegram interface |
| **Observability** | Langfuse + Cortex Dashboard | Trace inspection, session replay, LLM evaluation scoring, system health monitoring |
| **Memory** | GBrain | Long-term knowledge graph via Markdown files across 4 sources (luke, amy, shared, default). PGLite engine with Ollama embeddings. Sync daemon + dream cycle |
| **Config** | GitHub (two-repo system) | Public repo: installer, skeleton, docs. Private repo: full config, scripts, dashboard, nginx config. Brain content on private branches |

## Repository Architecture

| Repo | Visibility | Contents |
|------|-----------|----------|
| `hermes-cortex` | **Public** | Installer (`install.sh`), skeleton config, architecture docs, bump-version script. No secrets or brain data |
| `hermes-cortex-private` | **Private** | Full system config (`config.yaml`), dashboard (Flask + JS), nginx config, 13 utility scripts, all cron setups |
| `brain-*` branches on private repo | **Private** | Brain content on `brain-luke`, `brain-amy`, `brain-shared`, `brain-default` branches. Each is a clean single-commit orphan branch synced via gbrain |

## Services

| Service | Port | Purpose | Stack |
|---------|------|---------|-------|
| Ollama | 11434 | Local LLM serving | Native macOS, launchd-managed |
| Hermes Gateway | — | Agent runtime | Python, gateway.run, launchd |
| Langfuse | 3001 | LLM trace observability | Docker Desktop (6 containers) |
| Cortex Dashboard | 8901 | System + Langfuse companion | Flask + pure JS/HTML |
| nginx | 80/443 | Reverse proxy for all services | Homebrew, launchd |
| GBrain Sync | — | Memory sync daemon | Bun, PGLite, launchd (2min interval) |

## External Access

All external services are accessed via nginx on custom ports with TLS + basic auth:

| Port | Service | Auth Required |
|------|---------|--------------|
| 11002 | Langfuse (primary) | Yes |
| 11003 | Cortex Dashboard | Yes |

## Design Principles

1. **Thin harness, fat skills** — The agent framework stays lean; the value lives in well-crafted skills and memory
2. **Visibility first** — Every agent action is observable via Langfuse traces + evaluation scores
3. **Persistence by design** — Config, skills, memory, and brain content are all version-controlled
4. **Self-improving loop** — The agent creates skills from patterns, optimizes through cron-driven analysis
5. **Separation of concerns** — Public (installer/docs) ≠ Private (config/scripts) ≠ Brain (content on branches)
6. **No PII in history** — Both repos have been surgically scrubbed via git-filter-repo; brain data only on private branches

---

**See also:** [Security Guide → `docs/SECURITY.md`](./SECURITY.md)
