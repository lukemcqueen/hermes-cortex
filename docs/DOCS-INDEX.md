# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `docs/setup-reference.md` | Deployment setup, health monitoring pipeline, Ollama model tier |
| `docs/operations-reference.md` | Operations — inbox architecture, Agent Bus, offline code, common tasks |
| `docs/agent-onboarding.md` | Agent onboarding — step-by-step guide for client-only agents to connect to Moses and the fleet |
| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/fleet-update-protocol.md` | **NEW** — Fleet update bus protocol: UPDATE_REQUEST/RESULT, FIX_REQUEST/RESULT schemas for Moses→fleet orchestration |
| `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
| `ops/scripts/agent/agent-message-handler.py` | **Agent message handler** — polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK; runs cortex-update, posts results |
| `install-crons.sh` | Cron registration — creates agent-message-handler cron (inbox polling), auto-remediation, health, memory sync, scoring, and audit crons |
| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts |
| `install.sh` | Single-command installer (idempotent, safe to re-run) |
| `ops/install/install.sh` | Main installer script (moved from root in v2.0.0) |
| `ops/scripts/` | Health checks, watchdogs, governance, installers — 160+ scripts across subdirectories |

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall (pf + fail2ban), recovery |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview — layers, services, port map, security stack |
| `docs/bus-architecture.md` | **Bus Architecture (quick ref)** — agent message queue topology, auth, ACL, message flow. Full doc at `docs/reference/cortex-bus-config.md` |
| `docs/reference/cortex-bus-config.md` | **Cortex Bus Config Guide** — full architecture reference: fleet topology, auth model, ACL/permissions, message consumption, forwarder, troubleshooting |
| `ops/scripts/lib/cortex_bus.py` | **Cortex Bus library** — shared HTTP API wrapper over the Agent Bus: bus_send/bus_read/bus_archive/bus_list_queues |
| `docs/esther-bus-setup.md` | **Esther Bus Backup** — orchestrator-only guide: bus server, nginx with X-Forwarded-User, Postgres setup, verification |
| ~~`docs/agent-inbox-setup.md`~~ | Agent inbox setup (legacy — file deleted; superseded by Agent Bus → `docs/agent-bus-setup.md`) |
| `docs/service-layer-decision.md` | **Fleet-wide decision:** User-level systemd (Linux) / LaunchAgents (macOS) for all agent services. Full HC-Party architecture review with 6-role weighted matrix. |
| `docs/linux-service-layer.md` | Linux service layer guide — user-level systemd, reboot survivability, template, migration from stale system units |
| `docs/macos-service-layer.md` | macOS service layer guide — LaunchAgents vs LaunchDaemons, plist templates, migration guide, fleet service map |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation model — gbrain source isolation, federated vs isolated sources, pointer pattern integration |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `docs/deploy-registry-pattern.md` | Multi-repo deploy registry — public/private split, brain-* branches, sync workflow |
| `docs/cloud-deploy.md` | Cloud deployment runbook — AWS EC2 + Hetzner Cloud: sizing, ports, SSL, verification, costs, recovery |
| `ops/deploy/cloud-init.yaml` | Cloud VM bootstrap — Ubuntu 24.04 user-data: Docker, Ollama, Hermes, Langfuse, UFW, systemd |
| `docs/templates/SOUL.md` | SOUL.md template (v3.1.0) — identity, mission, traits, 33 behavioral principles, patterns & pitfalls, scripture, final directive. Canonical source used by cortex-doctor.py for sync validation |
| `ops/deploy/bootstrap.sh` | **Interactive** Linux server bootstrap — bare Ubuntu → full stack: Docker, Ollama, nginx, SSL, fail2ban, UFW, secrets, hardening |
| `ops/deploy/ansible/provision.yml` | Ansible provisioning playbook — idempotent: 16 tasks, 6 tags, nginx+ollama templates |
| `docs/multica-assessment.md` | Multica assessment — multi-agent, multi-server orchestration platform evaluation |
| `docs/design/DESIGN.md` | Design conventions — typography, color, spacing, UI (light/dark modes) |
| `docs/deprecated-profile-model.md` | Archived v1.x profile-per-project model — legacy migration reference |
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |

## Operations

| Doc | Description |
| `docs/new-harness.md` | Task Harness architecture proposal — deterministic task control: state machine, lease, interruption, completion gates |
| `docs/research/new_harness/` | Harness spec research — consolidated v2 requirements, Moses/Esther specs, ChatGPT draft |
| `mcp-servers/loop-gov-mcp.py` | Harness v3 governance MCP server — state machine, ledger, issues, interruption protocol, completion gates |
| `docs/troubleshooting.md` | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse, Linux |
| `docs/fleet-reference.md` | Fleet status table — agent worker status across all fleet members |
| `docs/operations-reference.md` | Agent inbox message format — field reference, subject prefixes, priority levels |
| `docs/fleet-reference.md` | Auto-remediation pipeline cron schedule reference |
| `docs/operations-reference.md` | Governance & Quality cron schedule reference — scoring, auditing, enforcement |
| `docs/fleet-reference.md` | Deployment-specific cron schedule reference — update, status, deploy crons |
| `docs/skills-manifest-reference.md` | Skills manifest — how to manage project-level skills via YAML |
| `docs/reference/skill-loading.md` | Skill loading protocol — every agent loads skills on session start |
| `docs/reference/cortex-bus-config.md` | **↗ Bus config guide** — install, auth resolution, message format, cron auth, troubleshooting |
| `docs/reference/after-completing-work-6-questions.md` | **Pre-ship checklist** — 6 validation questions every change must pass before end_change |
| `docs/reference/session-todo-protocol.md` | **Session todo discipline** — durable cross-session todo management protocol |
| `docs/gbrain-stale-lock-detection.md` | gbrain stale lock file detection & auto-recovery — root cause, automated fix via service-recovery, manual diagnostics |
| `docs/cron-schedules.md` | **Canonical cron schedule reference** — every cron, schedule, type, script, delivery. Update whenever schedules change. |
| `docs/cron-jobs-reference.md` | **Cron jobs inventory** — all cron jobs with name, type, schedule, and purpose (extracted from AGENTS.md) |
| `docs/cron-format-standard.md` | **Cron output format standard** — required format for all LLM-driven cron outputs: header, phases, cost footer, [SILENT]. Cross-references the cron-format-standard skill. |
| `docs/cron-job-recipes.md` | 10 reusable cron recipes — Bible reading, system alerts, memory pruning, morning briefing, and more |
| `docs/computer-specs.md` | Hardware specs guide — RAM tiers, recommended models (Intel vs Apple Silicon), ZIM content bundles |
| `ops/install/deploy/docker-compose.langfuse.yml` | Langfuse v3 Docker stack — ClickHouse, MinIO, Redis, Postgres |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/offline-travel-stack.md` | Offline knowledge scenarios — jungle travel, development, kid learning |
| `ops/offline/code-corpus/` | Per-language code snippets (26 languages, 386 files) — indexed by `offline_code` tool |
| `ops/offline/SKILL.md` | Offline-knowledge skill — cascade cache + kiwix ZIM usage protocol + Code Assistant |
| `ops/offline/prep-bible.sh` | Bible translation downloader — 55+ languages |
| `ops/offline/prep-hymns.sh` | Public domain hymn downloader — scores (PDF), notation (ABC), audio (MIDI) |
| `ops/offline/bible-parse.py` | Multi-strategy Bible text parser (PG, eBible, WEB formats) → structured JSON |
| `ops/offline/offline-reader.py` | Local web UI for Bible, hymns, and reference — zero dependencies, dark theme, fully offline |
| `ops/offline/auto-update.sh` | Silent auto-update for offline content — set-and-forget via cron |
| `ops/offline/offline_code.py` | Offline code assistant — search/generate from 518 curated code snippets across 32 categories via Ollama RAG |
| `ops/offline/prep-code.sh` | Build the code snippet corpus and vector index for offline coding |
| `ops/offline/code-corpus/generate.py` | Auto-discovers snippets modules, writes formatted .md snippet files with YAML frontmatter |
| `ops/web-cache/SKILL.md` | Web cache skill — local semantic cache for web_search and web_extract |
|  | **Legacy paths removed:** `deploy/` was a symlink to `ops/install/deploy/` — now canonical under `ops/`. `src/` was migrated to `core/` + `ops/` in v2.0.0. `runtime/` duplicated `core/` content and has been removed. |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Version manifest for all skills — planning pipeline + execution methodology |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `skills/` | Canonical skills directory — organized by domain in the repo |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/AGENTS.seed.md` | AGENTS.md seed template — agent contract, loop governance, skill loading |
| `docs/templates/skills.yaml` | Skills manifest seed template — always + on_task sections |
| `docs/templates/USER.seed.md` | User profile seed template — preferences, context, projects |
| `docs/templates/memory-readme.seed.md` | Memory scoring rubric seed — compact version of memory/README.md |
| `docs/templates/gitignore.brain` | Standard .gitignore for brain sources |
| `docs/templates/com.hermes.cortex-dashboard.plist` | Launchd plist for Cortex Dashboard |
| `docs/templates/com.docker.docker.plist` | Launchd plist for Docker Desktop auto-start |
|| `docs/templates/com.hermes.health-push.plist` | Launchd plist — health vector push (every 10min, to Moses via Agent Bus) |
|| `docs/templates/com.hermes.gateway.plist` | Launchd plist — persistent Hermes Gateway daemon |
|| `docs/templates/skills/change-checklist/SKILL.md` | **Mandatory change-checklist skill** — load before every `end_change()`. AGENTS.md requires it. |

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
|| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
|| `docs/integration-audit.md` | Integration audit — path consistency, script map, agent notes for three-layer repo health |
||| `ops/scripts/` | Cron scripts, health checks, agent tools — 5 subdirectories: agent/, health/, install/, inbox/, manage/ |
||| `ops/scripts/lib/` | Shared Python libraries for fleet scripts — cortex_bus.py (bus HTTP API) |
|| `core/governance/` | Governance engine — loop-governance DB, scoring, policy enforcement |
|| `.gitignore` | Gitignore — excludes .agentkore, .env, secrets, brain data |
