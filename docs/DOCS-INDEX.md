# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

> **Privacy note (2026-08-24):** this public repo is a **framework** for
> others to implement their own strategies. Business strategy, internal
> decision records (elicitation, parties, plans, reviews, proposals), and
> host-specific implementation docs live in the **private** repo
> (`hermes-cortex-private`) — never here.

> **Documentation areas (2026-10-01):** docs are split by *currency*, not topic.
> `docs/` holds what is **current** — everything indexed below. `docs/older/`
> holds what is **historical** — dated records, deprecated/superseded designs,
> completed plans, migration records, and foreign-project design material
> (see `docs/older/README.md` for what belongs where and the move procedure).
> If a doc below describes live behaviour, it stays here; when it stops being
> true, it moves to `docs/older/` rather than being deleted.

---

## Getting Started

| Doc | Description |
|-----|-------------|
| `README.md` | Project overview, quick start, and links |
| `docs/PATTERNS.md` | **Enterprise agentic patterns — what you can take**: bad-actor IP blocklist, A2A bus messaging, RAG/token-cost caching, enforced governance, self-healing ops, threat pipeline — each with file paths and reading order |
| `CONTRIBUTING.md` | Agent contribution guide — how to make changes, add features, fix bugs, and push to the shared repo |
| `AGENTS.md` | Agent guidelines — read by AI tools on session start |
| `docs/setup-reference.md` | Deployment setup, health monitoring pipeline, Ollama model tier |
| `docs/operations-reference.md` | Operations — inbox architecture, Agent Bus, offline code, common tasks |
| `docs/agent-onboarding.md` | Agent onboarding — step-by-step guide for client-only agents to connect to the bus and fleet |
| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/fleet-update-protocol.md` | **NEW** — Fleet update bus protocol: UPDATE_REQUEST/RESULT, FIX_REQUEST/RESULT schemas for Moses→fleet orchestration. **Shared orchestrator inbox** (`inbox_orchestrator`) for failover-aware escalation |
| `docs/runbooks/blocklist-cleanup-ddos-relax.md` | **Blocklist cleanup & DDoS relaxation (2026-08-08)** — legit users blocked on Kustos/Gisu/Joseph. DDoS burst relaxation (manual templates), scanner now adds ONLY fail2ban-confirmed abusers, allow-list guard, `classify-blocked-ips.sh` evidence-based review tool. Run on Joseph (primary discovery host) |
| `docs/runbooks/push-metrics-nginx-deploy.md` | **Push-metrics sink (port xx005) (2026-09-23)** — `agent-push-metrics` failing 1000+ runs. Root cause: the xx005 block was bundled into the opt-in extras template and never deployed, plus an `unbound variable` crash on hosts without a fallback URL. Both fixed in-repo (own `metrics-sink.conf` template + default-on gate + bounded client alerting); the host-side deploy needs root. |
| `docs/runbooks/cortex-env-migration.md` | **cortex env migration (2026-10-01)** — the ONE canonical cortex env (`~/hermes-cortex/.env`): the deployed dir holds no `.env`, `cortex-bus.conf` is a symlink to it, `~/.hermes/.env` is Hermes-owned. How any agent applies it on Linux/macOS (just run `cortex-update.sh` — it runs `consolidate-env.sh`), how to verify (`--check` + the doctor's `cortex env` check), and the 4 refactor changes to implement. |
| `docs/runbooks/cron-bridge-migration.md` | **cron → HC bridge migration (2026-10-01)** — move a host's `no_agent` crons off the Hermes `cronjob` scheduler onto systemd user timers. The one-owner rule (**remove the Hermes entry, do not merely pause it**), the `timers.target.wants` ownership marker, the per-host procedure, the 3-part verification, and the installer/doctor guards that make removal safe. |
| `docs/runbooks/context-integration.md` | **Context integration — memory + session for ANY coding agent (2026-10-02)** — the agent-facing runbook: the harness **registry** (`ops/install/harnesses/registry.yaml` + generator) as the single source, the access-layer rule (MCP for MCP-native harnesses, **CLI + extension for Pi — Pi has NO MCP client**), the second hinge (**the harness owns WHEN a checkpoint is written**, never the model), per-harness install/verify, failure modes, and boundaries. |
| `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
| `ops/scripts/agent/agent-message-handler.py` | **Agent message handler** — polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK; runs cortex-update, posts results |
| `ops/scripts/install-crons.sh` | Cron registration — creates agent-message-handler cron (inbox polling), auto-remediation, health, memory sync, scoring, and audit crons |
| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts, HERMES_SERVICES for nginx service split |
| `ops/install/install.sh` | Main installer script (moved from root in v2.0.0) |
| `docs/pre-commit-scoring.md` | Pre-commit scoring hook — TDD cycle scoring, loop governance integration, and enforcement model |
| `ops/scripts/` | Health checks, watchdogs, governance, installers — scripts across subdirectories |
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
| `docs/adr/0005-messaging-gateway.md` | **ADR-0005: Unified Messaging Gateway** — one daemon owns all messaging apps; agents bus-only; envelope v1; per-bot ACLs + advisory locks |
| `docs/design/messaging-gateway.md` | **Messaging gateway design** — party-converged architecture (adapters, routing, envelope, reliability, security, migration, MVP) |
| `docs/external/README.md` | **External context** — what exists outside the repo: third-party services + where credentials live. Never values. (Env var NAMES live in `docs/env-vars.md`) |
| `docs/design/agent-interop.md` | **Agent interoperability — the abstraction layer (2026-10-02)** — the standing constraint (design for N coding agents). ONE implementation (contract) + per-host ADAPTERS that add no semantics; where host-local extras are allowed and how they must declare themselves; the 8 rules (each a bug that shipped); the checklist for adding a host via `ops/install/harnesses/registry.yaml`; and the drift-guard tests that enforce it. Motivated by `mem_context` existing TWICE, so one copy was a phantom. |
| `docs/design/mycortex-DESIGN.md` | mycortex knowledge-brain design |
| `docs/design/mycortex-dream-layer.md` | Dream-layer design |
| `docs/design/mycortex-dream-task-bridge.md` | Dream→task bridge |
| `docs/design/mycortex-multi-tenancy.md` | mycortex multi-tenancy |
| `docs/design/learning-ledger.md` | Learning ledger design |
| `docs/design/skills-session-manager-v2.md` | Skills session manager v2 |
| `docs/design/bus-scale/` | Bus scale-out design (sharding, circuit-breaker, long-poll, metrics) |
| `docs/older/deprecated-profile-model.md` | Deprecated profile model — history |
| `docs/cloud-deploy.md` | Cloud deployment reference |
| `docs/design/frontieragent-gap-analysis.md` | **FrontierAgent gap analysis (2026-09-14)** — benchmark vs our core: inference-aware context management, bounded orchestration, sandbox safety, SDK seam; prioritized recommendations |
| `docs/design/moral-architecture-adaptation.md` | **Moral architecture adaptation (2026-09-24)** — the "Moral Architecture for Autonomous Systems" report translated onto Hermes Cortex's L0–L7 stack, adapted for LLM agents; 9 prioritized architecture changes (layer-tagged guardrail registry, failure-propensity register, independent evaluator, refusal metrics, Jubilee TTLs, unannounced probes) + open questions |
| `docs/reference/moral-architecture/` | **Moral Architecture for Autonomous Systems** — source PDF (gitignored) + working digest (16 theses, 7-layer stack, placement rule, seams, practical program, Scripture index) |
| `docs/design/moral-architecture-slices.md` | **Moral architecture story/slice build plan (2026-09-24)** — the 9 adaptation gaps sliced into deepseek-flash-sized BUILD/CHECK tasks (failure-propensity register, layer-tagged registry, refusal metrics, seam ownership, permission TTL, independent evaluator, unannounced probe, evidence allowlist) |
| `docs/design/independent-adversarial-verifier.md` | **Independent adversarial verifier spec (2026-09-24)** — the M6 "separate evaluator" gap made concrete: a different model + fixed orchestrator-owned prompt + orchestrator-triggered cron, built entirely on existing infra (cronjob, LLM_CRON_PROVIDER, loop-governance DB, orchestrator-only paths). 5 BUILD/CHECK slices + 3 open questions |
| `docs/design/component-hermes-separation.md` | **Component↔Hermes separation (2026-09-30)** — scope-1+2 plan to make every fleet component resolve/schedule without requiring the Hermes runtime: sever the `hermes_*` import seam (cortex_lib vendoring) + standalone scheduler/gateway/MCP hosting; the route-around-Hermes migration rule applied to the present fleet |
| `docs/design/cortex-gateway.md` | **cortex-gateway (2026-10-01)** — the decoupled gateway: standalone poll→dispatch→reply daemon with pluggable agent backends (hermes first, pi/steadfaste next); the migration target for the in-process `hermes_cli.main gateway run` loop. CR1 transport (parity with msg-gateway.py) + CR2 BackendAdapter seam built |
| `docs/design/cortex-memory-session-mcp.md` | **cortex memory & session as MCP servers (S2c, 2026-10-01)** — gives Pi (and any non-Hermes harness) the two capabilities that today exist only inside a Hermes process: `cortex-mem-mcp.py` (the five `mem_*` tools over the existing mycortex-mem store) and `cortex-session-mcp.py` (checkpoint/restore **plus** searchable session history). Why MCP beats a bespoke service, the two tool surfaces, the stores (existing memory schema + a new `sessions` schema reusing `v004` embeddings), slices S2c-a…d, and the one-owner risk of two writers on one store |
| `docs/design/gateway-envelope-verification.md` | **Gateway envelope verification (2026-10-01, CR7 design)** — the consumer-side trust boundary that turns the gateway's `gateway_sig` from declared into enforced: one `accept()` decision fn + typed trust (`kind:user_message`) + one enforcement point per consumer class (shim for coding agents/Pi/steadfaste-tui, MCP for hermes) + a language-neutral canonicalization recipe with golden vectors |

## Operations

| Doc | Description |
|-----|-------------|
| `docs/operations-reference.md` | Operations reference — inbox, bus, offline code, tasks |
| `docs/fleet-reference.md` | Fleet reference — crons, agents, remediation |
| `docs/pipeline-reference.md` | Pipeline reference |
| `docs/troubleshooting.md` | Troubleshooting guide |
| `docs/older/troubleshooting-stale-inbox-api.md` | Stale inbox API troubleshooting |
| `docs/cron-format-standard.md` | Cron output format standard |
| `docs/axi-agent-ergonomics.md` | **NEW (2026-08-24)** — AXI agent-ergonomics principles (from the AXI project): 10-principle distillation + mapping to Cortex surfaces — TOON output, minimal schemas, structured errors, ambient context |
| `docs/cron-job-recipes.md` | Cron job recipes |
| `docs/cron-schedules.md` | Cron schedules reference |
| `docs/cron-jobs-reference.md` | Cron jobs reference |
| `docs/deploy-registry-pattern.md` | Deploy registry pattern |
| `docs/git-enforcement.md` | Git enforcement model |
| `docs/loop-governance-reference.md` | Loop governance reference |
| `docs/seeding-brain-content.md` | Seeding brain content |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `docs/offline-code/` | Offline code search + generation |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Skills manifest — all shared skills (auto-generated: 369 skills, 55 categories) |
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
| `docs/enforcer-known-issues.md` | **Known issues** in the governance enforcer / loop-gov lock machinery (check_lock false-clear, orphan TTL window, PID-marker buildup, close-out gap, no-session-id fail-closed, post-deploy skill-credit loss, mtime-fingerprint false invalidation) + how to self-check any host with `probe-gate-logic.py` — verified on moses 2026-09-17 / 2026-09-23 |

## Development

| Doc | Description |
|-----|-------------|
| `docs/prd/` | Product requirements (PRD-001…006) |
| `docs/design/` | Design documents |
| `docs/plans/` | Implementation plans — **private** (moved 2026-08-24) |
