# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `install.sh` | Single-command installer (idempotent, safe to re-run) |
| `check-system.sh` | System compatibility check before installing |

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall, recovery |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview — layers, services, design principles |
| `docs/design/DESIGN.md` | Design conventions — typography, color, spacing, UI |

## Operations

| Doc | Description |
|-----|-------------|
| `docs/troubleshooting.md` | 17 common issues and fixes for Docker, Dashboard, install, nginx, memory, and Linux |
| `docs/cron-job-recipes.md` | 10 reusable cron recipes — Bible reading, system alerts, memory pruning, morning briefing, and more |
| `docs/computer-specs.md` | Hardware specs guide — RAM tiers, recommended models, ZIM content bundles |
| `docker-compose.langfuse.yml` | Langfuse v3 Docker stack — ClickHouse, MinIO, Redis, Postgres |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |
| `docs/offline-travel-stack.md` | Offline knowledge scenarios — jungle travel, development, kid learning |
| `docs/research/first-install-prompt-log.md` | First install prompt log |
| `offline/SKILL.md` | Offline-knowledge skill — cascade cache + kiwix ZIM usage protocol |
| `web-cache/SKILL.md` | Web cache skill — local semantic cache for web_search and web_extract |
| `memory/patterns.md` | Recurring code and design patterns |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/MEMORY.seed.md` | Memory file seed template — pointer pattern starter |
| `docs/templates/USER.seed.md` | User profile seed template — preferences, context, projects |
| `docs/templates/gitignore.brain` | Standard .gitignore for brain sources |
| `docs/templates/com.hermes.cortex-dashboard.plist` | Launchd plist for Cortex Dashboard |
| `docs/templates/com.docker.docker.plist` | Launchd plist for Docker Desktop auto-start |

## Legal & Compliance

| Doc | Description |
|-----|-------------|
| `docs/THIRD_PARTY_LICENSES.md` | Third-party licenses for all referenced Docker images, installed software, PyPI packages, and offline content |

## Development

| Doc | Description |
|-----|-------------|
| `scripts/` | OS abstraction scripts (`os-config.sh`, `service-writer.sh`, `install-ollama.sh`, `install-nginx.sh`, `install-gbrain-sync.sh`) plus utility scripts (heartbeat, memory sync, health checks, scoring) |
| `.gitignore` | Gitignore — excludes .agentkore, .env, secrets, brain data |
