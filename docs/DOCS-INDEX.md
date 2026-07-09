# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `docs/setup-reference.md` | Deployment setup across Luke's multi-machine fleet |
|| `docs/operations-reference.md` | Operations — inbox architecture, offline code, common tasks |
|| `docs/agent-onboarding.md` | Agent onboarding — step-by-step guide for client-only agents to connect to Moses and the fleet |
|| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts |
| `install.sh` | Single-command installer (idempotent, safe to re-run) |
| `src/scripts/ (flat shared libs), src/scripts/agent/, health/, install/, inbox/, manage/install/check-system.sh` | System compatibility check before installing |

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall (pf + fail2ban), recovery |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview — layers, services, port map, security stack |
| `docs/service-layer-decision.md` | **Fleet-wide decision:** User-level systemd (Linux) / LaunchAgents (macOS) for all agent services. Full HC-Party architecture review with 6-role weighted matrix. |
| `docs/linux-service-layer.md` | Linux service layer guide — user-level systemd, reboot survivability, template, migration from stale system units |
| `docs/macos-service-layer.md` | macOS service layer guide — LaunchAgents vs LaunchDaemons, plist templates, migration guide, fleet service map |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation model — gbrain source isolation, federated vs isolated sources, pointer pattern integration |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `docs/deploy-registry-pattern.md` | Multi-repo deploy registry — public/private split, brain-* branches, sync workflow |
| `docs/design/DESIGN.md` | Design conventions — typography, color, spacing, UI (light/dark modes) |
| `docs/deprecated-profile-model.md` | Archived v1.x profile-per-project model — legacy migration reference |
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |

## Operations

| Doc | Description |
|-----|-------------|
|| `docs/troubleshooting.md` | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse, Linux |
|| `docs/gbrain-stale-lock-detection.md` | gbrain stale lock file detection & auto-recovery — root cause, automated fix via service-recovery, manual diagnostics |
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
| `src/offline/offline_code.py` | Offline code assistant — search/generate from 518 curated code snippets across 32 categories via Ollama RAG |
| `src/offline/prep-code.sh` | Build the code snippet corpus and vector index for offline coding |
| `src/offline/code-corpus/generate.py` | Auto-discovers snippets modules, writes formatted .md snippet files with YAML frontmatter |
| `src/web-cache/SKILL.md` | Web cache skill — local semantic cache for web_search and web_extract |
| `deploy/patches/hermes-langfuse-cost-fixes.patch.md` | Patch notes for Langfuse cost calculation fixes |

## Skills

| Doc | Description |
|-----|-------------|
|| `docs/SKILLS-MANIFEST.md` | Version manifest for all skills — planning pipeline + execution methodology |
|| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
|| `src/skills/` | Canonical skills directory — organized by domain in the repo |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/MEMORY.seed.md` | Memory file seed template — pointer pattern starter |
| `docs/templates/USER.seed.md` | User profile seed template — preferences, context, projects |
| `docs/templates/memory-readme.seed.md` | Memory scoring rubric seed — compact version of memory/README.md |
| `docs/templates/gitignore.brain` | Standard .gitignore for brain sources |
| `docs/templates/com.hermes.cortex-dashboard.plist` | Launchd plist for Cortex Dashboard |
| `docs/templates/com.docker.docker.plist` | Launchd plist for Docker Desktop auto-start |
| `docs/templates/com.hermes.health-push.plist` | Launchd plist — health vector push (every 10min, to Moses inbox) |
| `docs/templates/com.hermes.gateway.plist` | Launchd plist — persistent Hermes Gateway daemon |

## Legal

| Doc | Description |
|-----|-------------|
| `docs/THIRD_PARTY_LICENSES.md` | Third-party licenses for all referenced Docker images, installed software, PyPI packages, and offline content |

## Git Enforcement

| Doc | Description |
|-----|-------------|
| `docs/git-enforcement.md` | Pre-commit scoring + pre-push pull-before-push hooks — install, bypass, troubleshooting |

## Development

| Doc | Description |
|-----|-------------|
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `src/scripts/` | Shared libraries + 5 subdirectories: agent/, health/, install/, inbox/, manage/ — cron scripts, health checks, installers, inbox tools, management utilities |
| `.gitignore` | Gitignore — excludes .agentkore, .env, secrets, brain data |
