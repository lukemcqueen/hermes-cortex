# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

> **Privacy note (2026-08-24):** this public repo is a **framework** for
> others to implement their own strategies. Business strategy, internal
> decision records (elicitation, parties, plans, reviews, proposals), and
> host-specific implementation docs live in the **private** repo
> (`hermes-cortex-private`) — never here.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `docs/setup-reference.md` | Deployment setup, health monitoring pipeline, Ollama model tier |
| `docs/operations-reference.md` | Operations — inbox architecture, Agent Bus, offline code, common tasks |
| `docs/agent-onboarding.md` | Agent onboarding — step-by-step guide for client-only agents to connect to the bus and fleet |
| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/fleet-update-protocol.md` | **NEW** — Fleet update bus protocol: UPDATE_REQUEST/RESULT, FIX_REQUEST/RESULT schemas for Moses→fleet orchestration. **Shared orchestrator inbox** (`inbox_orchestrator`) for failover-aware escalation |
| `docs/runbooks/blocklist-cleanup-ddos-relax.md` | **Blocklist cleanup & DDoS relaxation (2026-08-08)** — legit users blocked on Kustos/Gisu/Joseph. DDoS burst relaxation (manual templates), scanner now adds ONLY fail2ban-confirmed abusers, allow-list guard, `classify-blocked-ips.sh` evidence-based review tool. Run on Joseph (primary discovery host) |
| `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
| `ops/scripts/agent/agent-message-handler.py` | **Agent message handler** — polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK; runs cortex-update, posts results |
| `ops/scripts/install-crons.sh` | Cron registration — creates agent-message-handler cron (inbox polling), auto-remediation, health, memory sync, scoring, and audit crons |
| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts, HERMES_SERVICES for nginx service split |
| `ops/install/install.sh` | Main installer script (moved from root in v2.0.0) |
| `docs/pre-commit-scoring.md` | Pre-commit scoring hook — TDD cycle scoring, loop governance integration, and enforcement model |
| `ops/scripts/` | Health checks, watchdogs, governance, installers — scripts across subdirectories |
| `core/cortex_bus/metrics.py` | **Bus metrics module** — prometheus_client definitions + async push client. Imported by bus server for queue-level observability |
| `ops/install/deploy/docker-compose.victoria-metrics.yml` | **VictoriaMetrics + Grafana stack** — Docker compose: metrics storage (3mo retention) + visualization dashboard. Grafana at :3030 |

## Documentation Routing

Canonical destination for workflow-produced artifacts. Internal decision
records (elicitation, plans, reviews, proposals) route to the **private**
repo; this public repo carries only framework docs (PRDs, design, reference).

| Artifact | Destination | Producing skill |
|----------|-------------|-----------------|
| Party — decision | `docs/design/` | `architecture-review` |
| PRD | `docs/prd/` | `product-requirements` |

## Security

| Doc | Description |
|-----|-------------|
| `docs/SECURITY.md` | Security guide — ports, permissions, passwords, firewall (pf + fail2ban), recovery |
| `docs/THIRD_PARTY_LICENSES.md` | Third-party license attributions |
| `docs/pinned-repo-hooks.md` | Pinned repo hooks — enforcement hooks that must stay pinned |
| `docs/symlink-policy.md` | Symlink policy — where symlinks are allowed/forbidden |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview |
| `docs/agent-architecture.md` | Agent roles, bus, cron rules |
| `docs/agent-memory-pointer-pattern.md` | Pointer-memory pattern (MEMORY.md → mycortex) |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation design |
| `docs/design/DESIGN.md` | Design principles |
| `docs/design/task-workflow.md` | Task workflow design (task model v1/v2) |
| `docs/design/task-lifecycle-v2.md` | Task lifecycle v2 — statuses, transitions, stale sweep |
| `docs/design/task-model-v3.md` | **Task model v3** — orchestrator-intelligence / worker-execution, claim/report/verify, compete mode |
| `docs/adr/README.md` | **ADR convention** — durable fleet decisions (model contract, MAX_COST guard, bus v2 API). Read before re-deriving WHY the system is shaped this way |
| `docs/external/README.md` | **External context** — env var NAME registry + external services (payment processor, credentials locations). Never values |
| `docs/design/mycortex-DESIGN.md` | mycortex knowledge-brain design |
| `docs/design/mycortex-dream-layer.md` | Dream-layer design |
| `docs/design/mycortex-dream-task-bridge.md` | Dream→task bridge |
| `docs/design/mycortex-multi-tenancy.md` | mycortex multi-tenancy |
| `docs/design/learning-ledger.md` | Learning ledger design |
| `docs/design/skills-session-manager-v2.md` | Skills session manager v2 |
| `docs/design/bus-scale/` | Bus scale-out design (sharding, circuit-breaker, long-poll, metrics) |
| `docs/deprecated-profile-model.md` | Deprecated profile model — history |
| `docs/cloud-deploy.md` | Cloud deployment reference |

## Operations

| Doc | Description |
|-----|-------------|
| `docs/operations-reference.md` | Operations reference — inbox, bus, offline code, tasks |
| `docs/fleet-reference.md` | Fleet reference — crons, agents, remediation |
| `docs/pipeline-reference.md` | Pipeline reference |
| `docs/troubleshooting.md` | Troubleshooting guide |
| `docs/troubleshooting-stale-inbox-api.md` | Stale inbox API troubleshooting |
| `docs/cron-format-standard.md` | Cron output format standard |
| `docs/cron-job-recipes.md` | Cron job recipes |
| `docs/cron-schedules.md` | Cron schedules reference |
| `docs/cron-jobs-reference.md` | Cron jobs reference |
| `docs/deploy-registry-pattern.md` | Deploy registry pattern |
| `docs/git-enforcement.md` | Git enforcement model |
| `docs/loop-governance-reference.md` | Loop governance reference |
| `docs/docker-registry-cache.md` | Docker registry cache |
| `docs/seeding-brain-content.md` | Seeding brain content |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/offline-code/` | Offline code search + generation |
| `docs/offline-travel-stack.md` | Offline travel stack (kept as reusable pattern) |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Skills manifest — all shared skills |
| `docs/skills-manifest-reference.md` | Skills manifest reference |
| `docs/continuous-skill-suggestion.md` | Continuous skill suggestion |
| `docs/agent-learning-submissions.md` | Agent learning submissions |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/SOUL.md` | Canonical SOUL.md template |
| `docs/templates/AGENTS.seed.md` | AGENTS.md seed |
| `docs/templates/MEMORY.seed.md` | MEMORY.md seed |
| `docs/templates/USER.seed.md` | USER.md seed |
| `docs/templates/AGENTS-loop-governance.md` | AGENTS loop-governance template |
| `docs/templates/task-contract.md` | Task contract template |
| `docs/templates/repo-efficiency-block.md` | Repo efficiency block (marker-guarded, additive) |
| `docs/templates/memory-readme.seed.md` | Memory README seed |

## Legal

| Doc | Description |
|-----|-------------|
| `LICENSE` | Project license |
| `docs/THIRD_PARTY_LICENSES.md` | Third-party licenses |

## Git Enforcement

| Doc | Description |
|-----|-------------|
| `docs/pinned-repo-hooks.md` | Pinned enforcement hooks |
| `docs/pre-commit-scoring.md` | Pre-commit scoring |
| `docs/git-enforcement.md` | Git enforcement model |

## Development

| Doc | Description |
|-----|-------------|
| `docs/prd/` | Product requirements (PRD-001…006) |
| `docs/design/` | Design documents |
| `docs/plans/` | Implementation plans — **private** (moved 2026-08-24) |
