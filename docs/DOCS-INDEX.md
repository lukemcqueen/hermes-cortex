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
| `docs/troubleshooting.md` | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse data, memory, Linux, pf firewall, fail2ban |
| `docs/cron-job-recipes.md` | 10 reusable cron recipes — Bible reading, system alerts, memory pruning, morning briefing, and more |
| `docs/computer-specs.md` | Hardware specs guide — RAM tiers, recommended models, ZIM content bundles |
| `docker-compose.langfuse.yml` | Langfuse v3 Docker stack — ClickHouse, MinIO, Redis, Postgres |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |
| `docs/offline-travel-stack.md` | Offline knowledge scenarios — jungle travel, development, kid learning |
| `docs/research/first-install-prompt-log.md` | First install prompt log |
|| `offline/SKILL.md` | Offline-knowledge skill — cascade cache + kiwix ZIM usage protocol. Includes Code Assistant section (386 snippets, 26 languages) |
|| `offline/prep-bible.sh` | Bible translation downloader — 55+ languages, small (4-10 MB per translation). Auto-parses to structured JSON via `bible-parse.py` |
|| `offline/prep-hymns.sh` | Public domain hymn downloader — scores (PDF), notation (ABC), lyrics (XML), audio (MIDI) |
|| `offline/bible-parse.py` | Multi-strategy Bible text parser — PG, eBible, raw verse, WEB formats. Generates structured JSON for the reader |
|| `offline/offline-reader.py` | Local web UI for browsing Bible, hymns, and reference — zero dependencies, dark theme, works fully offline |
|| `offline/auto-update.sh` | Silent auto-update for offline content — online-aware, set-and-forget via cron |
|| `offline/offline_code.py` | Offline code assistant — search/generate from 386 curated code snippets across 26 languages via Ollama RAG |
|| `offline/prep-code.sh` | Build the code snippet corpus and vector index for offline coding |
|| `offline/code-corpus/snippets/` | Per-language Python modules defining the full code corpus. Modular: add `*_snippets.py`, re-run `generate.py` and `prep-code.sh` |
|| `offline/code-corpus/generate.py` | Auto-discovers snippets modules, writes formatted .md snippet files with YAML frontmatter |
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
