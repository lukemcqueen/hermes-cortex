# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `install.sh` | Single-command installer (idempotent, safe to re-run) |
| `src/scripts/check-system.sh` | System compatibility check before installing |

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall (pf + fail2ban), recovery |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview — layers, services, port map, security stack |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation model — gbrain source isolation, federated vs isolated sources, pointer pattern integration |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `docs/deploy-registry-pattern.md` | Multi-repo deploy registry — public/private split, brain-* branches, sync workflow |
| `docs/design/DESIGN.md` | Design conventions — typography, color, spacing, UI (light/dark modes) |
| `docs/deprecated-profile-model.md` | Archived v1.x profile-per-project model — legacy migration reference |
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |

## Operations

| Doc | Description |
|-----|-------------|
| `docs/troubleshooting.md` | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse, Linux |
| `docs/cron-job-recipes.md` | 10 reusable cron recipes — Bible reading, system alerts, memory pruning, morning briefing, and more |
| `docs/computer-specs.md` | Hardware specs guide — RAM tiers, recommended models (Intel vs Apple Silicon), ZIM content bundles |
| `deploy/docker-compose.langfuse.yml` | Langfuse v3 Docker stack — ClickHouse, MinIO, Redis, Postgres |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/offline-travel-stack.md` | Offline knowledge scenarios — jungle travel, development, kid learning |
| `docs/offline-code-tutorials/` | Per-language code snippets in `src/offline/code-corpus/` (26 languages, 386 files) |
| `src/offline/SKILL.md` | Offline-knowledge skill — cascade cache + kiwix ZIM usage protocol + Code Assistant |
| `src/offline/prep-bible.sh` | Bible translation downloader — 55+ languages |
| `src/offline/prep-hymns.sh` | Public domain hymn downloader — scores (PDF), notation (ABC), audio (MIDI) |
| `src/offline/bible-parse.py` | Multi-strategy Bible text parser (PG, eBible, WEB formats) → structured JSON |
| `src/offline/offline-reader.py` | Local web UI for Bible, hymns, and reference — zero dependencies, dark theme, fully offline |
| `src/offline/auto-update.sh` | Silent auto-update for offline content — set-and-forget via cron |
| `src/offline/offline_code.py` | Offline code assistant — search/generate from 386 curated code snippets via Ollama RAG |
| `src/offline/prep-code.sh` | Build the code snippet corpus and vector index for offline coding |
| `src/offline/code-corpus/generate.py` | Auto-discovers snippets modules, writes formatted .md snippet files with YAML frontmatter |
| `src/web-cache/SKILL.md` | Web cache skill — local semantic cache for web_search and web_extract |
| `deploy/patches/hermes-langfuse-cost-fixes.patch.md` | Patch notes for Langfuse cost calculation fixes |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Version manifest for all 21 skills — planning pipeline + execution methodology |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `.hermes-cortex/skills/` | Project-specific Hermes skills |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/MEMORY.seed.md` | Memory file seed template — pointer pattern starter |
| `docs/templates/USER.seed.md` | User profile seed template — preferences, context, projects |
| `docs/templates/memory-readme.seed.md` | Memory scoring rubric seed — compact version of memory/README.md |
| `docs/templates/gitignore.brain` | Standard .gitignore for brain sources |
| `docs/templates/com.hermes.cortex-dashboard.plist` | Launchd plist for Cortex Dashboard |
| `docs/templates/com.docker.docker.plist` | Launchd plist for Docker Desktop auto-start |

## Legal

| Doc | Description |
|-----|-------------|
| `docs/THIRD_PARTY_LICENSES.md` | Third-party licenses for all referenced Docker images, installed software, PyPI packages, and offline content |

## Development

| Doc | Description |
|-----|-------------|
| `src/scripts/` | OS abstraction scripts (os-config.sh, service-writer.sh, install-ollama.sh, install-nginx.sh, install-gbrain-sync.sh) + utility scripts (heartbeat, memory sync, bootstrap-brain, check-memory-budget, health checks, scoring) |
| `.gitignore` | Gitignore — excludes .agentkore, .env, secrets, brain data |
