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
| `docs/daily-bible-reading.md` | Daily bible reading cron — no_agent script setup, section-scoping contract, troubleshooting |
| `docs/agent-onboarding.md` | Agent onboarding — step-by-step guide for client-only agents to connect to Moses and the fleet |
| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/fleet-update-protocol.md` | **NEW** — Fleet update bus protocol: UPDATE_REQUEST/RESULT, FIX_REQUEST/RESULT schemas for Moses→fleet orchestration. **Shared orchestrator inbox** (`inbox_orchestrator`) for failover-aware escalation |
| `docs/fallback-architecture-survey.md` | **Moses fallback architecture** — failover survey, Esther's warm-standby bus, gaps & approaches |
| `docs/backup-orch-failover-runbook.md` | **Failover & recovery runbook** — step-by-step: Moses-down activation, drain, Moses-back reintegration. Auto-detection now via `cortex-bus-failover-watchdog` cron (all agents) + `tests/test-failover-drill.py` |
| `docs/cert-monitoring.md` | SSL/TLS cert monitoring — how certs are checked, renewed, alerted. Cert checks gated to cert-holder hosts only (joseph/gisu/kustos) |
| `docs/archive/` | Archived/superseded design docs (PRD-005 v1, etc.) |
| `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
| `ops/scripts/agent/agent-message-handler.py` | **Agent message handler** — polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK; runs cortex-update, posts results |
|| `ops/scripts/install-crons.sh` | Cron registration — creates agent-message-handler cron (inbox polling), auto-remediation, health, memory sync, scoring, and audit crons |
|| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts, HERMES_SERVICES for nginx service split |
|| `install.sh` | Single-command installer (idempotent, safe to re-run) |
|| `ops/install/install.sh` | Main installer script (moved from root in v2.0.0) |
|| `docs/pre-commit-scoring.md` | Pre-commit scoring hook — TDD cycle scoring, loop governance integration, and enforcement model |
|| `ops/scripts/` | Health checks, watchdogs, governance, installers — 160+ scripts across subdirectories |
|| `ops/scripts/manage/push-metrics.sh` | **Agent metrics push script** — Prometheus-format system metrics POSTed to central VictoriaMetrics. Used by all agents for observability. |
|| `core/cortex_bus/metrics.py` | **Bus metrics module** — prometheus_client definitions + async push client. Imported by bus server for queue-level observability. |
|| `ops/install/deploy/docker-compose.victoria-metrics.yml` | **VictoriaMetrics + Grafana stack** — Docker compose: metrics storage (3mo retention) + visualization dashboard. Grafana at :3030. |
| `docs/push-metrics-setup.md` | **Push metrics setup guide** — VictoriaMetrics + Grafana, per-agent push, nginx orch config |

## Documentation Routing

Canonical destination for workflow-produced artifacts (canonical table —
proposal `docs/proposals/2026-08-06-docs-artifact-routing.md`). Every new doc
must be registered in this index.

| Artifact | Destination | Producing skill |
|----------|-------------|-----------------|
| Elicitation + stories | `docs/elicit/` | `requirements-elicitation` |
| Plans | `docs/plans/` | `dev-plan` (via `agent-flow` planning pattern) |
| Party — decision | `docs/design/` | `architecture-review` |
| Party — elicitation-combined | `docs/elicit/` | `architecture-review` |
| Code / repo-health / gap reviews | `docs/reviews/` | `repo-health-review`, `code-review`, `engineering-approach` ref |
| PRD | `docs/prd/` | `product-requirements` |
| Proposals | `docs/proposals/` | (submitted by agents for orchestrator review) |

**`docs/reviews/` (new, 2026-08-06):** durable review records —
`docs/reviews/README.md` (stub + routing table), `docs/reviews/repo-health-review-2026-07-23.md` (moved from docs root).

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall (pf + fail2ban), recovery |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview — layers, services, port map, security stack |
| `docs/bus-architecture.md` | **Bus Architecture (canonical role matrix)** — who has what (server/MCP/HTTP client), ACL (incl. shared `inbox_orchestrator`), topology, message flow |
| `docs/reference/cortex-bus-config.md` | **Cortex Bus Config Guide** — full architecture reference: fleet topology, auth model, ACL/permissions, message consumption, forwarder, troubleshooting |
| `ops/scripts/lib/cortex_bus.py` | **Cortex Bus library** — shared HTTP API wrapper over the Agent Bus: bus_send/bus_read/bus_archive/bus_list_queues |
| `docs/esther-bus-setup.md` | **Esther Bus Backup** — orchestrator-only guide: bus server, nginx with X-Forwarded-User, Postgres setup, verification |
| ~~`docs/agent-inbox-setup.md`~~ | Agent inbox setup (legacy — file deleted; superseded by Agent Bus → `docs/orch-bus-setup.md`) |
| `docs/service-layer-decision.md` | **Fleet-wide decision:** User-level systemd (Linux) / LaunchAgents (macOS) for all agent services. Full HC-Party architecture review with 6-role weighted matrix. |
| `docs/linux-service-layer.md` | Linux service layer guide — user-level systemd, reboot survivability, template, migration from stale system units |
| `docs/macos-service-layer.md` | macOS service layer guide — LaunchAgents vs LaunchDaemons, plist templates, migration guide, fleet service map |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation model — gbrain source isolation, federated vs isolated sources, pointer pattern integration |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `docs/deploy-registry-pattern.md` | Multi-repo deploy registry — public/private split, brain-* branches, sync workflow |
| `docs/cloud-deploy.md` | Cloud deployment runbook — AWS EC2 + Hetzner Cloud: sizing, ports, SSL, verification, costs, recovery |
| `ops/deploy/cloud-init.yaml` | Cloud VM bootstrap — Ubuntu 24.04 user-data: Docker, Ollama, Hermes, Langfuse, UFW, systemd |
| `docs/templates/SOUL.md` | SOUL.md template — identity, mission, traits, 18 behavioral principles with pain-of-skip enforcement, procedural appendix, scripture, final directive. Canonical source; soul-merge.py auto-merges updates into agent copies |
| `ops/deploy/bootstrap.sh` | **Interactive** Linux server bootstrap — bare Ubuntu → full stack: Docker, Ollama, nginx, SSL, fail2ban, UFW, secrets, hardening |
| `ops/deploy/ansible/provision.yml` | Ansible provisioning playbook — idempotent: 16 tasks, 6 tags, nginx+ollama templates |
|| `docs/multica-assessment.md` | Multica assessment — multi-agent, multi-server orchestration platform evaluation |
|| `docs/plans/fleet-command-verifier.md` | **Fleet Command Verifier** — design plan: dispatch recording, periodic verification, retry, Telegram alerts for hc exec/send |
| `docs/design/DESIGN.md` | Design conventions — typography, color, spacing, UI (light/dark modes) |
| `docs/deprecated-profile-model.md` | Archived v1.x profile-per-project model — legacy migration reference |
| `docs/agent-memory-pointer-pattern.md` | Compressed pointers + agent brain for unlimited context |
| `docs/elicit/2026-08-01_mycortex-elicitation.md` | **mycortex elicitation (pass 1)** — requirements for gbrain replacement: domain decomposition, RICE/MoSCoW, source model, decommission plan |
| `docs/design/mycortex-DESIGN.md` | **mycortex design v2** — gbrain replacement: git-truth + shared-Postgres index + thin Python; schema v001 (fail-closed RLS, role split), migration runner, 9-phase decommission, test strategy. 2× 6-role party-reviewed |
| `docs/design/mycortex-multi-tenancy.md` | **mycortex multi-tenancy** — per-profile reader roles (`mycortex_reader_<profile>`, LOGIN INHERIT), RLS-on-CURRENT_USER isolation, agent migration steps (grant migration + verification), safe-by-construction rationale. Added 2026-08-06 (Luke: "100 employees, one brain") |
| `docs/design/mycortex-dream-layer.md` | **mycortex dream layer** — 3-tier optional LLM cron serendipity layer (nightly/weekly/monthly), write-back to `~/brain/<profile>/dreams/` + INDEX, per-agent removable via `install-dream-crons.sh` |
| `docs/design/mycortex-dream-task-bridge.md` | **dream → task bridge (implemented 2026-08-06, migrated to tasks schema same day)** — turns dream output into actionable tasks: Option A (monthly knowledge-gap → "learn X" tasks, cap 4) + Option B (insight triage all tiers, cap 2), dedup + caps + tenant-scoping enforced in `dream-task-bridge.py` via `task-db.py` → `tasks.tasks`. Formerly `mycortex-dream-todo-bridge.md` (bus.todos era; retired with the old todo system — see `docs/design/task-workflow.md`) |
| `docs/elicit/2026-08-06_todo-workflow-elicit.md` | **enterprise todo/workflow elicitation** — Luke directive: all agents have tasks, zero bus nomenclature. 4 refinement rounds: agent×repo×scope → +fleet visibility → +kanban → +MCP → +project/repo/target split → scope orthogonality. Luke rename directive 2026-08-06: "task" throughout. Party handoff |
| `docs/design/task-workflow.md` | **task workflow design (party-reviewed 2026-08-06)** — enterprise task system: `tasks` schema on per-host mycortex-postgres (v001, version-gated), profile-role CRUD + RLS, status-canonical lifecycle, honest local-only fleet semantics (git-backed private-repo roadmap), guarded bus.todos migration, `task-db.py` + `task-mcp.py` (ALL agents), test plan L0-L3, AC-1..AC-12. 6-role party: 6.0/10 as elicited → conditional go with B-1..B-10 mandatory fixes |
| `docs/elicit/2026-08-06_task-lifecycle-v2-elicit.md` | **task lifecycle v2 elicitation (2026-08-06)** — story/slices hierarchy, lifecycle automation (before/during/switching/after), bus-commands-as-tasks, Telegram visibility. Fast mode, 4 locked decisions D-1..D-4, 13F+7NF, 4 US with ACs. Party handoff |
| `docs/elicit/2026-08-06_task-lifecycle-v2-party.md` | **task lifecycle v2 party verdict (2026-08-06)** — 6-role HC-Party: conditional go 6.40/10 (Architect 6.5, Security 6, SRE 6, Domain 6.5, Product 7, QA 4→6.5). Weighted matrix, QA/Product conflict resolution, 26 findings (B-1..B-5, R-1..R-22, M-1..M-12), cost estimate, rollout gate |
| `docs/design/task-lifecycle-v2.md` | **task lifecycle v2 design (party-reviewed 2026-08-06)** — v005 schema (parent_id/kind, paused, correlation_id, task_events, transition+tenant triggers, transactional), transition matrix in DB write path, event trail contract, bus integration (allowlist, create-before-archive, dual consumers), shared `lib/telegram_notify.py`, security invariants (prompt-injection channel, tenant coherence), migration/skew handling, S1..S8 implementation plan, L0/L1/L2 tests, single-host→dogfood→fleet rollout gate |
| `docs/elicit/2026-08-01_mycortex-stories.md` | **mycortex stories (16 vertical slices)** — S-001..S-016 with Given/When/Then AC: harness, schema, sync, search, CLI+/brain, lessons, deploy, parity, decommission, semantic v1.1, MCP v1.2. **S-014 semantic shipped 2026-08-06** (v004 + `ask`/`embed`) |
| `ops/services/mycortex/schema/v004__embeddings.sql` | **mycortex schema v004 (v1.1 semantic)** — `content_chunks.embedding vector(768)` + model/dim, UNIQUE (id,model,dim) partial, HNSW cosine index; extension pinned to public. Added 2026-08-06 (S-014) |
| `ops/services/mycortex/schema/mycortex.sql` | **mycortex schema v001** — sources/pages/content_chunks/source_grants/ingest_log/query_log/schema_version; fail-closed RLS (FORCE + policies), role split (admin/ingest/reader), PII gate CHECK, `log_query()` SECURITY DEFINER |
| `ops/install/deploy/docker-compose.mycortex.yml` | **mycortex-postgres compose** — dedicated hermes-cortex-owned Postgres (db `mycortex`, role `mycortex`, port 15432). Replaces the old gbrain-postgres container (2026-08-05) |
| `ops/scripts/manage/migrate-gbrain-postgres-to-mycortex.sh` | **fleet migration script** — idempotent per-host gbrain-postgres→mycortex-postgres: dump, container swap, restore, re-apply roles/RLS/grants, env update, verify. Old container stopped (not removed) for rollback |
| `ops/services/mycortex/migrate.py` | **mycortex migration runner** — schema_version-gated psql runner, invoked by cortex-update.sh after file sync (the DDL path); `--db-name` override for test DBs |
| `ops/scripts/manage/mycortex-parity.py` | **mycortex parity harness** — golden known-answer set runner: `--mode baseline` (records gbrain results → `tests/fixtures/gbrain-baseline.json`), `--mode check` (pass rate vs mycortex). **Retired as a gate 2026-08-03** (gbrain deprecated) — now a manual regression fixture |
| `tests/fixtures/golden-queries.json` | **Golden known-answer set** — 28 queries (18 federated hermes-cortex, 10 isolated moses) with expected top-3 paths, pinned to source SHAs |
| `tests/test-mycortex-schema.sh` | **S-003 AC battery** — scratch-DB RLS isolation-leak (as mycortex_reader), PII gate, role split, idempotent migration |
| `tests/test_mycortex_parity.py` | **S-001 parity tests** — fixture-engine pass-rate/gate coverage, golden-set integrity |

## Operations

| Doc | Description |
|| `docs/new-harness.md` | Task Harness architecture proposal — deterministic task control: state machine, lease, interruption, completion gates |
|| `docs/harness-features-spec.md` | **Harness features spec** — task state machine, MCP server, completion gates, adversarial tests, priority hierarchy |
|| `docs/research/new_harness/` | Harness spec research — consolidated v2 requirements, Moses/Esther specs, ChatGPT draft |
| `docs/loop-governance-reference.md` | Governance reference — MCP tools vs CLI, scoring guidelines, enforcement layers (no structural override — allow_tool_override not in production config) |
| `docs/governance-improvement-plan.md` | **Friction-driven governance roadmap** — session-mined friction taxonomy, mapped guardrails, P0/P1/P2 enforcement plan (correction→guardrail scanner, read-only whitelist, verify-before-declare gate) |
| `docs/governance-improvement-plan-gaps.md` | **Multi-role gap review of the improvement plan** — 3-role HC-Party findings (3 SHOWSTOPPER / 7 MAJOR / 5 MINOR), corrected implementation order, Esther adversarial-verify evaluation. Corrects plan premises: P0-2 as written was an RCE hole; corpus is 18,857 user msgs not 416k. §10 queues P1-A/P1-B; P1-A resolved 2026-07-31 (sticky marker per governance lock, atomic lock writes, purge safety, session_type differentiation) |
| `docs/guardrail-registry.json` | **Machine-readable guardrail registry (P0-1a)** — correction-class → enforcement artifact mapping, consumed by `agent-session-correction-scan.py` |
| `docs/continuous-skill-suggestion.md` | **Design doc** — structural skill reminders during edits. After fixed enforcer bootstrap gate, the next gap: agents don't reload skills mid-task. Touch-trace writer + end_change suggestions |
| `mcp-servers/loop-gov-mcp.py` | Harness v3 governance MCP server — state machine, ledger, issues, interruption protocol, completion gates |
| `plugins/governance-enforcer/README.md` | Governance enforcer plugin — pre_tool_call hook, lock file protocol, fixed-path + PID handoff, two-phase discovery, block matrix, stale lock purge |
| `ops/scripts/manage/purge-stale-governance-locks.py` | Stale governance lock purge script — removes expired lock files and orphan symlinks from crashed sessions |
|  ~~`ops/scripts/manage/prune-soul-profiles.py`~~ | ~~SOUL.md profile pruner~~ *(file removed — not in repo)* |
| `docs/troubleshooting.md` | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse, Linux |
| `docs/fleet-reference.md` | Fleet status table, cron schedules, auto-remediation, deploy schedules |
| `docs/operations-reference.md` | Inbox message format, governance & quality cron schedules |
| `docs/skills-manifest-reference.md` | Skills manifest — how to manage project-level skills via YAML |
| `docs/reference/skill-loading.md` | Skill loading protocol — every agent loads skills on session start |
| `docs/reference/cortex-bus-config.md` | **↗ Bus config guide** — install, auth resolution, message format, cron auth, troubleshooting |
| `docs/reference/after-completing-work-6-questions.md` | **Pre-ship checklist** — 6-questions verification: arrays, cleanup, docs, syntax, doctor, push/deploy |
| `docs/reference/session-todo-protocol.md` | **Session todo protocol** — todo() lifecycle: read durable file, update on cycles, write back at session end |
| `docs/gbrain-stale-lock-detection.md` | gbrain stale lock file detection & auto-recovery — root cause, automated fix via service-recovery, manual diagnostics |
| `docs/cron-schedules.md` | **Canonical cron schedule reference** — every cron, schedule, type, script, delivery (incl. explicit telegram targets for script-created crons, mycortex dream layer tiers + optional installer). Also the **Delivery Policy for LLM crons** — issues only, never status; exact `[SILENT]` when nothing actionable (Luke directive 2026-08-06). Update whenever schedules change. LLM-cron **stagger convention** (2026-08-07): base schedules shown; minute rewritten per host at install. |
| `docs/cron-jobs-reference.md` | **Cron jobs inventory** — all cron jobs with name, type, schedule, and purpose (extracted from AGENTS.md) |
| `docs/cron-format-standard.md` | **Cron output format standard** — required format for all LLM-driven cron outputs: header, phases, cost footer, [SILENT]. Cross-references the cron-format-standard skill. |
| `docs/cron-job-recipes.md` | 10 reusable cron recipes — Bible reading, system alerts, memory pruning, morning briefing, and more |
| `docs/agent-architecture.md` | **Agent architecture & role model** — orchestrator, backup, server-agent, dev-agent capability matrix |
| `docs/orch-bus-setup.md` | Agent Bus setup guide — PGMQ queues, auth, fleet wiring (orchestrator-only) |
| `docs/model-tier-strategy.md` | Model selection strategy — two-model Ollama stack, rationale, tier architecture |
| `docs/health-server-optimization.md` | Health vector server — keepalive, buffering, nginx config tuning |
| `docs/orch-bus-setup.md` | **Orchestrator bus setup** — dedicated bus server for Moses |
| `docs/orch-backup-bus-setup.md` | **Orchestrator backup bus** — Esther warm-standby bus failover |
| `docs/symlink-policy.md` | **Symlink map** — `~/.hermes/` ↔ `~/.hermes-cortex/` directory orientation |
| `docs/docker-registry-cache.md` | Docker registry mirror — local cache for pull throughput |
| `docs/troubleshooting-stale-inbox-api.md` | Stale inbox API diagnostics — port conflicts, cert renewal impact |
| `docs/governance-hardening-proposal.md` | Governance hardening proposal — structural override analysis, adversarial attack |
| `docs/proposals/2026-08-06-provider-timeout-fix.md` | **Provider timeout fix proposal** — fleet-wide deepseek request timeout (LLM cron hang class), ready-to-apply patch |
| `docs/proposals/2026-08-06-docs-artifact-routing.md` | **Docs artifact routing proposal** — canonical docs/ routing for review/gap-analysis/elicit/party/docs workflows. ✅ APPLIED 2026-08-06 (moses) |
| `docs/gbrain-postgres-migration.md` | gbrain Postgres migration — schema, migration procedure |
| `docs/gbrain-v2-taxonomy.md` | gbrain v2 taxonomy — brain source categories and tag conventions |
| `docs/agent-learning-submissions.md` | **Agent learning submissions** — how agents submit ad-hoc learnings via ~/brain/learnings/pending/ |
| `docs/pre-task-sequence-mandatory-before-every-task.md` | Pre-task sequence reference table — relocated from AGENTS.md during doc pruning |
| `docs/contact-protocol-how-to-reach-orchestrator.md` | Contact protocol — how agents reach the orchestrator, relocated from AGENTS.md during doc pruning |
| `docs/pipeline-reference.md` | **Skill lifecycle pipeline** — collection, evaluation, upgrade flow, cron tables |
| `docs/computer-specs.md` | Hardware specs guide — RAM tiers, recommended models (Intel vs Apple Silicon), ZIM content bundles |
| `ops/install/deploy/docker-compose.langfuse.yml` | Langfuse v3 Docker stack — ClickHouse, MinIO, Redis, Postgres |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/offline-travel-stack.md` | Offline knowledge scenarios — jungle travel, development, kid learning |
| `ops/offline/code-corpus/` | Per-language code snippets (26 languages, 521 files) — indexed by `offline_code` tool |
| `ops/offline/SKILL.md` | Offline-knowledge skill — cascade cache + kiwix ZIM usage protocol + Code Assistant |
| `ops/offline/prep-bible.sh` | Bible translation downloader — 55+ languages |
| `ops/offline/prep-hymns.sh` | Public domain hymn downloader — scores (PDF), notation (ABC), audio (MIDI) |
| `ops/offline/bible-parse.py` | Multi-strategy Bible text parser (PG, eBible, WEB formats) → structured JSON |
| `ops/offline/offline-reader.py` | Local web UI for Bible, hymns, and reference — zero dependencies, dark theme, fully offline |
| `ops/offline/auto-update.sh` | Silent auto-update for offline content — set-and-forget via cron |
| `ops/offline/offline_code.py` | Offline code assistant — search/generate from 521 curated code snippets across 32 categories via Ollama RAG |
| `ops/offline/prep-code.sh` | Build the code snippet corpus and vector index for offline coding |
| `ops/offline/code-corpus/generate.py` | Auto-discovers snippets modules, writes formatted .md snippet files with YAML frontmatter |
| `ops/web-cache/SKILL.md` | Web cache skill — local semantic cache for web_search and web_extract |
| | **Legacy paths removed:** `deploy/` was a symlink to `ops/install/deploy/` — now canonical under `ops/`. `src/` was migrated to `core/` + `ops/` in v2.0.0. `runtime/` duplicated `core/` content and has been removed. |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Version manifest for all skills — planning pipeline + execution methodology |
| `docs/seeding-brain-content.md` | Brain directory templates and starter content — get from 0 pages to searchable knowledge |
| `skills/` | Canonical skills directory — organized by domain in the repo |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/AGENTS.seed.md` | AGENTS.md seed template — project context, conventions, SOUL.md relationship principles |
| `docs/templates/SOUL.md` | **Canonical SOUL.md template** — agent identity, mission, principles. Modify for all agents. |
| `docs/templates/skills.yaml` | Skills manifest seed template — always + on_task sections. Modify for all agents. |
| `docs/templates/USER.seed.md` | User profile seed template — preferences, context, projects |
| `docs/templates/memory-readme.seed.md` | Memory scoring rubric seed — compact version of memory/README.md |
| `docs/templates/gitignore.brain` | Standard .gitignore for brain sources |
| `docs/templates/SOUL.md` | **SOUL.md template** — agent identity, mission, behavioral principles, communication style, scripture/memory tips |
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
| `docs/pinned-repo-hooks.md` | Pinned repo hooks — file refresh, Library/node_modules crawl exclusions, doctor check 7c, hooksPath-guard carve-out |
| `.hermes-cortex/hooks/post-merge` | Auto-deploy hook (via `core.hooksPath`) — runs `cortex-update.sh ` after every `git pull`. Prevents stale deploys |

## Development

| Doc | Description |
|-----|-------------|
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `docs/integration-audit.md` | Integration audit — path consistency, script map, agent notes for three-layer repo health |
| `ops/scripts/` | Cron scripts, health checks, agent tools — 5 subdirectories: agent/, health/, install/, inbox/, manage/ |
| `ops/scripts/lib/` | Shared Python libraries for fleet scripts — cortex_bus.py (bus HTTP API) |
| `core/governance/` | REMOVED July 2026 — MCP-based governance replaces it |
| `.gitignore` | Gitignore — excludes .agentkore, .env, secrets, brain data |
