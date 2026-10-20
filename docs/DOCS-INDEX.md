# Documentation Index

A lightweight map of all project documents. Files are grouped by topic.

> **Privacy note (2026-08-24):** this public repo is a **framework** for
> others to implement their own strategies. Business strategy, internal
> decision records (elicitation, parties, plans, reviews, proposals), and
> host-specific implementation docs live in the **private** repo
> (`hermes-cortex-private`) — never here.

> **Documentation areas (2026-10-20):** docs are split by *currency*, not topic.
> `docs/` holds what is **current** — the prose docs indexed below. `docs/older/`
> holds what is **historical** — dated records, deprecated/superseded designs,
> completed plans, migration records, and foreign-project design material
> (see `docs/older/README.md` for what belongs where, the move procedure, and
> the running list of what has been archived). If a doc below describes live
> behaviour, it stays here; when it stops being true it moves to `docs/older/`
> rather than being deleted.
>
> **Two areas this index deliberately does not enumerate row by row:**
> `docs/evidence/` is the run-evidence **store** (dated captures, transcripts and
> runnable verifiers — see `docs/evidence/README.md`), and the `*-reference.md`
> files in `docs/` plus `docs/reference/` are machine-managed by
> `ops/scripts/agent/agents-doc-audit.py` (`--prune --apply`). Both are browsed by
> directory (`ls`, `search_files`), not from a hand-kept table that goes stale
> the moment a run lands.

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
| `docs/agent-session-lifecycle.md` | What a working session looks like — the two gates, the lock, commit/push/close-out, adversarial review, and the gotchas that cost real time |
| `docs/fleet-reference.md` | Fleet reference — cron jobs, agent summary, auto-remediation |
| `docs/fleet-update-protocol.md` | **NEW** — Fleet update bus protocol: UPDATE_REQUEST/RESULT, FIX_REQUEST/RESULT schemas for Moses→fleet orchestration. **Shared orchestrator inbox** (`inbox_orchestrator`) for failover-aware escalation |
| `docs/runbooks/blocklist-cleanup-ddos-relax.md` | **Blocklist cleanup & DDoS relaxation (2026-08-08)** — legit users blocked on Kustos/Gisu/Joseph. DDoS burst relaxation (manual templates), scanner now adds ONLY fail2ban-confirmed abusers, allow-list guard, `classify-blocked-ips.sh` evidence-based review tool. Run on Joseph (primary discovery host) |
| `docs/runbooks/push-metrics-nginx-deploy.md` | **Push-metrics sink (port xx005) (2026-09-23)** — `agent-push-metrics` failing 1000+ runs. Root cause: the xx005 block was bundled into the opt-in extras template and never deployed, plus an `unbound variable` crash on hosts without a fallback URL. Both fixed in-repo (own `metrics-sink.conf` template + default-on gate + bounded client alerting); the host-side deploy needs root. |
| `docs/runbooks/cortex-env-migration.md` | **cortex env migration (2026-10-01, updated 2026-10-17)** — the ONE canonical cortex env (`~/hermes-cortex/.env`): the deploy dir carries the sanctioned back-compat symlink `~/.hermes-cortex/.env → canonical`, `cortex-bus.conf` retired 2026-10-17, `~/.hermes/.env` is Hermes-owned. How any agent applies it on Linux/macOS (just run `cortex-update.sh` — it runs `consolidate-env.sh`), how to verify (`--check` + the doctor's `cortex env` check), and the refactor changes to implement. |
| `docs/runbooks/review-triage-jev.md` | **Review triage — the System One judge in the close-gate (2026-10-02)** — the typed `/v1/systemone` contract (typed questions in, typed answers out; answer ids validated against question ids exactly), the per-finding question triples (`cites_artifact` noul, `class`, `severity`), `NOUL_TRUE` composed in the **caller**, the MEDIUM+-blocks/LOW-annotates policy, how to enable it (`ADVERSARIAL_TRIAGE_MODEL` + `TYPESAFE_API_KEY`), the `min_tier: T2` gate that makes von ineligible until its tier is validated, and why every failure mode is fail-safe. **A chat-completions model cannot serve it.** Also covers the **pluggable reviewer backends** (`llm` | `agent`, with the read-only and no-self-review rules) and — updated 2026-10-06 — the **reviewer tiering by measured complexity**: light-but-complex changes use the fast `ADVERSARIAL_REVIEW_LIGHT_MODEL` (~1s) even on an `agent`-backend host while heavy/always-review changes keep the deep backend; the committed dogfood harness `ops/scripts/manage/dogfood-reviewer-tiering.py`. Also documents the **live-verified wire shapes**: `criteria` must be a DICT of option→definition (a list is HTTP 422), `model` is required, and answers carry `confidence`. It also documents **where the gate reads its config**: decoupled from Hermes — process env → the canonical cortex env → the deploy root → `~/.hermes/.env` last, read per call so a config change needs no restart. |
| `docs/runbooks/cron-bridge-migration.md` | **cron → HC bridge migration (2026-10-01)** — move a host's `no_agent` crons off the Hermes `cronjob` scheduler onto systemd user timers. The one-owner rule (**remove the Hermes entry, do not merely pause it**), the `timers.target.wants` ownership marker, the per-host procedure, the 3-part verification, and the installer/doctor guards that make removal safe. |
| `docs/runbooks/orch-bus-worker-rename.md` | **orch-backlog-driver → orch-bus-worker rename (2026-10-14)** — the orchestrator's autonomous bus worker (F-023): every agent's routed suggestions (PROPOSAL/ISSUES/IMPROVEMENTS/STRANDED_SKILL_LAND) become tracked tasks it drives to a verified close. Convention table, apply-per-host, verification, symptom→cause→fix. The cron was resumed (removed from NEVER_RESUME) — it powers the fleet skill-improvement loop. |
| `docs/runbooks/adversarial-review-passoff.md` | **Handing work to the adversarial reviewer (2026-10-13)** — how to submit material a reviewer can actually judge: paste evidence rather than describe it, lead with open questions, and answer a wrong finding with a measurement instead of editing working code |
| `docs/runbooks/context-integration.md` | **Context integration — memory + session for ANY coding agent (2026-10-02)** — the agent-facing runbook: the harness **registry** (`ops/install/harnesses/registry.yaml` + generator) as the single source, the access-layer rule (MCP for MCP-native harnesses, **CLI + extension for Pi — Pi has NO MCP client**), the second hinge (**the harness owns WHEN a checkpoint is written**, never the model), per-harness install/verify, failure modes, and boundaries. |
| `docs/runbooks/multi-session-isolation.md` | **Multiple sessions on one host without collisions (2026-10-02)** — why two sessions in one repo bonk (shared git index sweeps staged work; identical authorship makes commits unattributable; concurrent deploys strip the immutable flags), the principle (**scope what can be scoped, serialise what cannot**), the convention (**one session = one worktree = one branch = one identity**), the `session-identity.sh` helper, and the rule that `AGENT_NAME` is NEVER session-appended. |
| `docs/runbooks/cron-model-chain-repoint.md` | **LLM cron model-chain repoint (2026-10-02)** — a host's LLM crons landing on the wrong model, or a `⚠️ Provider fallback` banner. The three layers that hold a stale pin (host-local `.env` env chain, per-job pin in `jobs.json`, operator `fallback_providers`), why a **dead free-tier pin never fails but silently spends**, the `--unpin` procedure, the 3-part verification, pitfalls (`jobs.json` uses `id` not `job_id`; retired names still resolve as aliases; peak/off-peak; cache-hit economics), and rollback. |
| `docs/runbooks/health-throttle-false-unreachable.md` | **Health-endpoint throttle → false "Moses unreachable" (2026-10-04)** — nginx `:13007` health block rate-limits the fleet's own probes at their synchronized `:00`/`:30` ticks (`conn_limit 10` + `burst 10` keyed per client IP) → 503/499 the watchdog reads as "down" → recurring unreachable/reachable flapping. Fix: `geo` **allowlist in `hermes-zone-defs.conf`** keys the limit zones off `$limit_bypass` — fleet IPs get an empty key (nginx applies no limit), everyone else keeps the DDoS ceiling; plus the compatible watchdog debounce (`84794f85`). |
| `ops/install/harnesses/pi/ADDON-telegram-gateway.md` | **Telegram gateway for Pi (hc / steadfaste)** — macOS launchd walkthrough for a Pi backend on the cortex-gateway daemon: bot token env, `gateway.yaml`, launchd plist, the `KeepAlive` `SuccessfulExit=false` pitfall that breaks `/restart`, and verification steps. Distinct bot from Hermes so both gateways run in parallel with no 409 conflict |
| `ops/install/harnesses/pi/ADDON-deepseek-mcp.md` | **The host-local DeepSeek review MCP server** — NOT a cortex server and NOT installed by `install-pi-mcp.sh`; its source lives in a PRODUCT repo (`~/Developer/AI/steadfaste-s1-model/scripts/util/mcp_deepseek_server.py`) and hosts register it themselves as `deepseek` in `~/.pi/agent/mcp.json`. Registration shape, the `import mcp` interpreter trap and its check, and what `audit-pi-integration.sh` does and does not say about it. Reached from `harnesses/pi/IMPLEMENT.md` (the five-server section) so the agent reading the install steps also finds it |
| `ops/scripts/make-evidence.sh` | **Make the evidence shape the review can actually read.** Writes a standard evidence file — the exact command, its own `rc` (captured bare), the timestamp and a sha256 of the content (before the hash line itself) — then `make-evidence.sh --verify <file>` rechecks it. Small-by-construction and machine-checkable, so a reviewer (and a later agent) verifies by re-running one command instead of trusting a transcription. POSIX-sh portable: Linux and macOS (`sha256sum` or `shasum -a 256`), any repo, with or without Hermes/cortex. See `skills/devops/loop-governance/SKILL.md` |
| `ops/scripts/manage/review-material.py` | **See the review's material window BEFORE you submit.** Prints the bounded material for `merge-base origin/main..HEAD` file by file with the budget in force, lists the range's commits (so a same-repo peer's commits inside your range are visible), and exits 1 when a changed file would be shown with almost no body. Stdlib-only Python 3 + git: Linux and macOS, any repo, no Hermes/cortex required. Replaces guessing at the window — cycle 12307 spent six review rounds doing exactly that |
| `ops/install/requirements.txt` | **What belongs in the fleet python venv, DECLARED.** `~/.hermes-cortex/venv` is the venv cortex-update.sh registers every MCP server against, but nothing said what it should contain — so a host with a broken venv had no definition of "fixed". Measured from the repo's own imports: `mcp`, `PyYAML`, `fastapi`, `uvicorn`, `psycopg[binary]`, `pytest` |
| `docs/macos-service-layer.md` | **The macOS (launchd) service map — Titus's Mac only.** Titus (hostname `LAM2`, the developer machine) is the fleet's ONLY macOS host; every other host is Linux and belongs to `docs/linux-service-layer.md`. This lists all five plist templates and what each runs, plus the three launchd rules that each cost a broken service: **launchd expands nothing inside plist strings** (a literal `$HOME/…` is a job that never starts), `StandardOutPath` must be literal (so home-relative logs are appended inside the `/bin/bash -lc` command), and an XML comment may not contain a double hyphen (the plist stops parsing). Also the interpreter convention (fleet venv, then the guard) and the `/restart` difference (**75** under launchd, 0 under systemd). Referenced by `CONTRIBUTING.md` and the pre-commit docs audit |
| `docs/linux-service-layer.md` | **The Linux (systemd) service map.** User units in `~/.config/systemd/user/` only — a system-level copy puts a second poller on the bot token (409) or collides on the health port 8905. Lists `cortex-gateway.service` and `health-vector.service`, the `%h` rule, the fleet-venv + guard convention, and `Restart=always` semantics. The deliberate counterpart of the macOS file |
| `ops/scripts/manage/mcp_wiring.py` | **Audit MCP *wiring*, not presence.** A registration only starts a server if its command and argument script exist — a dead path loads nothing and says nothing (kustos: *"No loop-governance MCP tools in catalog"* while the doctor said PASS, because it only looked for the NAME, which also matches a *filename* in the args). Prints per server: paths exist? interpreter is the fleet venv? `--json` for hooks, `--orch` for orchestrator-only servers; exit 1 on a broken entry, 3 = could not verify. Its expected map is asserted to match the doctor's, so there is one source of truth. `cortex-doctor.py` reports it as `MCP wiring (<name>)` |
| `ops/scripts/lib/require-fleet-venv.sh` | **The shared guard every fleet launcher sources.** `require_fleet_venv <payload>…` names which piece is missing — the fleet interpreter (`~/.hermes-cortex/venv/bin/python3`, or its `python3 → python` symlink target), the payload, or a different `$HOME` — prints the HOME it resolved, prints the repair sequence, and exits **78 (EX_CONFIG)** instead of letting bash emit `line N: No such file or directory`. One file, because a per-launcher copy drifts; `tests/test_fleet_venv_launchers.py` fails the suite if a new launcher bare-execs the venv path. Troubleshooting entry: `docs/troubleshooting.md` |
| `ops/scripts/manage/fix-cortex-venv.py` | **Repair `~/.hermes-cortex/venv` on ANY host, verified by IMPORT.** Installs only what is MISSING, deciding by importing the module in the target interpreter — not by metadata or exit codes (`PyYAML` is a distribution name; `yaml` is the module). Prefers `uv`, falls back to the venv's own pip, runs `ensurepip` on a uv venv that has none. `--check` reports and changes **nothing** (rc=3 with the exact fix command); `--json` emits a hook-consumable last line. Round trip on an empty venv: 6 of 6 missing → repaired → imports all 6. `cortex-update.sh` now CREATES an absent venv and runs this to fill it, deferring a failure if it cannot. Found the need the hard way: the fleet venv here had no pytest and could not collect a test module (no fastapi) |
| `tests/run-tests.sh` | **The supported way to run the suite.** Capability-resolves the interpreter (a path is not a promise) and unsets `PYTHONPATH`/`PYTHONHOME`, because an INHERITED `PYTHONPATH` silently drops tests: measured 1818 collected with 4 collection errors contaminated vs 1846 with none clean — a foreign `site-packages` shadowing the venv's own build raises `ImportError` that reads like a broken host instead of a contaminated caller. Falls back to the deployed resolver **loudly** (a silent fallback swaps which code decides the interpreter), supplies `tests/` when handed only flags (pytest with no path scans `.git` and hangs — measured 400s+), propagates pytest's own rc, and exits 3 with `COULD NOT VERIFY` when no interpreter can import pytest — no interpreter, no verdict, never a pass |
| `tests/test_suite_collection_clean.py` | **Fails when the environment cannot COLLECT the whole suite.** A green run that tests less than it claims is worse than a red one: those 28 absent tests were reported behind `N passed`. Passes through `run-tests.sh`, fails loudly any other way from a contaminated session |
| `tests/test_lock_liveness_activity.py` | **Liveness is observed activity, in both directions.** A commit by the lock's own agent in the lock's own repo counts as activity (busy, not dead) and the lock is refreshed instead of purged; a peer repo, a peer's author, a non-repo path and an empty timestamp all count as NOT activity; and an idle lock still ages out — a fix that rescued every orphan would be worse than the deadlock it cures. Pins the `agent: "unknown"` case too, which would otherwise silently disable the check |
| `tests/test_run_tests_wrapper.py` | **The wrapper runs on macOS, in multi-repo sessions, and in repos with no cortex.** Runs the REAL wrapper in constructed environments: a fake repo with no `ops/scripts/lib` and no `~/.hermes-cortex`, resolved by a PATH python3 that can import pytest (and one that cannot → rc=3, `NOT a pass`). Plus a source scan for what macOS actually breaks on: bash 4 (`declare -A`, `mapfile`, `${var,,}`) and GNU-only flags (`readlink -f`, `date -d`, `sed -i` without a suffix, `grep -P`, `sha256sum`). Its first draft asserted "no `hermes-cortex` in the source" and failed correctly — naming the deployed fallback is not requiring it |
| `ops/scripts/manage/gateway-model-list.py` | **Enable or check the `/model` picker's list on ANY agent host** — derives the list from that host's own `pi --list-models`, prints the block by default (dry run), `--write` merges ONLY the `models` key (every other key preserved, idempotent), `--check` is the fleet sweep (blanks, duplicates, bad `page_size`; exit 1). python3 **stdlib only** — no PyYAML, no Hermes, no cortex venv — so the same file runs on Linux and macOS, Titus's pi included. Exit **3 = COULD NOT VERIFY** (no pi on PATH), never "no models". Enable-steps: `docs/design/cortex-gateway-parity.md` |
| `ops/scripts/sustainability/capture_evidence.py` | Re-runnable evidence for a day's briefing — runs the canonical checker, records its real stdout/exit code, the sha256 of each artifact and the source-URL and word counts into `verification-<date>.txt`. Deliberately prints `MISSING` for an absent artifact instead of staying silent. Tests: `tests/test_capture_evidence.py` |
| `ops/scripts/sustainability/gen_briefing.py` | Briefing markdown → .docx/.pdf renderer (python-docx + reportlab). Splits the md subset the brief uses (H1/H2, bullets, `**bold**`, rules) and linkifies markdown links so committed evidence carries no `/home/<user>` path. Tests: `tests/test_gen_briefing.py` |
| `ops/scripts/sustainability/write_cycle_evidence.py` | Builds the `cycle-evidence-<date>.md` pack in `docs/evidence/briefings/` — a self-contained pack (real diffs, checker stdout, test output, sha256 per artifact, PDF/DOCX text extraction) so the self-adversarial reviewer receives verbatim material rather than a prose assertion that evidence exists. **Emits no absolute host path**: ONE normaliser rewrites this host's home prefix to `~` on every emitted line — captured subprocess output and stderr tracebacks included — because the pack is committed to a public repo and the raw path both tripped the secret-leak detector on every refresh and left commands the next reader could not re-run. Tests: `tests/test_write_cycle_evidence.py` (both directions: the redaction, and that the command still names the interpreter it used) |
| `ops/scripts/sustainability/write_test_results.py` | Runs the four briefing suites under warnings-as-errors and commits their **unedited** stdout plus per-suite exit codes to the `test-results-<date>.txt` file in `docs/evidence/briefings/`, so "N tests pass" is an inspectable artifact. Returns non-zero if any suite fails. Tests: `tests/test_write_test_results.py` |
| `ops/scripts/manage/dogfood-reviewer-tiering.py` | Reviewer-tiering dogfood harness (2026-10-06) — runs the REAL `loop-gov-mcp.py` module (only the two leaf backends patched) and prints PASS for the tier decision matrix + light/heavy/always-review routing. Wired into `tests/test_reviewer_backends.py::test_tiering_dogfood_script`. Committed `538c596d` |
| `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
| `ops/scripts/agent/agent-message-handler.py` | **Agent message handler** — polls inbox for UPDATE_REQUEST, ROLLBACK_REQUEST, GIT_AUTH_CHECK; runs cortex-update, posts results |
| `ops/scripts/install-crons.sh` | Cron registration — creates agent-message-handler cron (inbox polling), auto-remediation, health, memory sync, scoring, and audit crons |
| `docs/env-vars.md` | Environment variable reference — CORTEX_* vars, SSL, deploy scripts, HERMES_SERVICES for nginx service split |
| `ops/install/install.sh` | Main installer script (moved from root in v2.0.0) |
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
| `docs/symlink-policy.md` | Symlink policy — where symlinks are allowed/forbidden |

## Architecture & Design

| Doc | Description |
|-----|-------------|
| `docs/architecture.md` | System architecture overview |
| `docs/agent-architecture.md` | Agent roles, bus, cron rules |
| `docs/agent-memory-pointer-pattern.md` | Pointer-memory pattern (MEMORY.md → mycortex) |
| `docs/knowledge-isolation-architecture.md` | Knowledge isolation design |
| `docs/design/DESIGN.md` | Design principles |
| `docs/design/adversarial-review-cost-reduction.md` | Plan (levers A/B/C) to scope the close review to the session's own blobs, unify tier+material bases, and add a local pre-close pre-flight — measured against cycles 12777/12779/12782 |
| `docs/design/task-workflow.md` | Task workflow design (task model v1/v2) |
| `docs/design/task-lifecycle-v2.md` | Task lifecycle v2 — statuses, transitions, stale sweep |
| `docs/design/task-model-v3.md` | **Task model v3** — orchestrator-intelligence / worker-execution, claim/report/verify, compete mode |
| `docs/adr/0001-model-contract-pricing.md` | ADR-0001 — the model contract + pricing decision |
| `docs/adr/0003-bus-api-v2-policy.md` | ADR-0003 — the Agent Bus v2 API policy |
| `docs/adr/TEMPLATE.md` | ADR template — status/date/author header, then context → decision → consequences |
| `docs/adr/README.md` | **ADR convention** — durable fleet decisions (model contract + pricing, bus v2 API). Read before re-deriving WHY the system is shaped this way |
| `docs/adr/0005-messaging-gateway.md` | **ADR-0005: Unified Messaging Gateway** — one daemon owns all messaging apps; agents bus-only; envelope v1; per-bot ACLs + advisory locks |
| `docs/design/messaging-gateway.md` | **Messaging gateway design** — party-converged architecture (adapters, routing, envelope, reliability, security, migration, MVP) |
| `docs/external/external-services.md` | External services — names and locations of what lives outside the repo (never values) |
| `docs/external/mcp-deepseek-review.md` | The DeepSeek adversarial-review MCP server — pattern, tool surface, where the key comes from |
| `docs/external/README.md` | **External context** — what exists outside the repo: third-party services + where credentials live. Never values. (Env var NAMES live in `docs/env-vars.md`) |
| `docs/design/agent-search.md` | **Agent search — one capability, two agent systems (2026-10-13)** — the search capability for BOTH hermes-cortex (Python) and steadfaste (Rust). Records the measured facts that decided the shape (`go` ABSENT, rustc 1.98.1, steadfaste IS Rust, `sqlite3` CLI ABSENT, crates.io reachable), the measured envelope (**5.9 MB binary · 5.2 MB idle RSS**, versus 100–250 MB for minimal SearXNG), the three operations and their exit-code contract (0 ran / 1 failed / **3 could not verify — never an empty list**), the two surfaces (CLI + MCP stdio, one dispatch, schemas derived), the per-system adapter plan, and the honest limits (no live SearXNG round trip yet; wiring pending). Implementation: `tools/fleet-search/`. |
| `docs/design/gateway-reply-path.md` | **The gateway reply path (2026-10-08)** — transport leg proven (a signed envelope in `out_<agent>` drained to Telegram with a `message_id` receipt); the agent-side producer is the remaining half |
| `docs/design/adding-an-agent.md` | Adding a backend to the gateway is config, not code — the `BackendAdapter` seam and the `gateway.yaml` **kind** spec |
| `docs/design/executor-abstraction.md` | Executor abstraction — agent-agnostic execution layer; Hermes is Executor Adapter #1 |
| `docs/design/pii-denylist-digests.md` | PII deny-list digests — how the enforcer's PII gate learns which strings to block without committing them to a public repo |
| `docs/design/claude-governance.md` | Claude agent governance equivalence — the same governance for a non-Hermes coding agent on the same host |
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
| `docs/reference/skill-loading.md` | Skill-loading procedure (pruned from AGENTS.md; full reference in `docs/skills-manifest-reference.md`) |
| `docs/reference/after-completing-work-6-questions.md` | The six post-work questions an agent answers before declaring a change done |
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
| `docs/pipeline-reference.md` | Pipeline reference — the four growth pipelines **plus** how an agent submits an ad-hoc learning (`agent-learning-submissions.md`, merged 2026-10-20) |
| `docs/troubleshooting.md` | Troubleshooting guide |
| `docs/older/troubleshooting-stale-inbox-api.md` | Stale inbox API troubleshooting |
| `docs/axi-agent-ergonomics.md` | **NEW (2026-08-24)** — AXI agent-ergonomics principles (from the AXI project): 10-principle distillation + mapping to Cortex surfaces — TOON output, minimal schemas, structured errors, ambient context |
| `docs/cron-job-recipes.md` | Cron job recipes |
| `docs/cron-schedules.md` | **Canonical schedule reference** for every cron (the stale table is archived at `docs/older/cron-jobs-reference.md`) |
| `docs/deploy-registry-pattern.md` | **The real deployment** — one repo, the `register()` map in `ops/scripts/cortex-update.sh`, the generated `deploy-manifest.tsv`, **and** how a component resolves a repo-relative sibling in both layouts (`repo-vs-deployed-paths.md`, merged 2026-10-20) |
| `docs/review-receipt-gate.md` | **Review receipt gate** — a push touching an always-review path needs a CLEAN review receipt for that exact range (review before push) |
| `docs/loop-governance-reference.md` | Loop governance reference |
| `docs/seeding-brain-content.md` | Seeding brain content |

## Knowledge & Offline

| Doc | Description |
|-----|-------------|
| `ops/offline/code-corpus/` | Offline code corpus + search index (`ops/offline/offline_code.py`, `ops/offline/prep-code.sh`) |

## Skills

| Doc | Description |
|-----|-------------|
| `docs/SKILLS-MANIFEST.md` | Skills manifest — all shared skills (auto-generated: 369 skills, 55 categories) |
| `docs/skills-manifest-reference.md` | Skills manifest reference |

## Templates

| Doc | Description |
|-----|-------------|
| `docs/templates/SOUL.md` | Canonical SOUL.md template |
| `docs/templates/AGENTS.seed.md` | AGENTS.md seed |
| `docs/templates/MEMORY.seed.md` | MEMORY.md seed |
| `docs/templates/USER.seed.md` | USER.md seed |
| `docs/templates/AGENTS-loop-governance.md` | AGENTS loop-governance template |
| `docs/templates/adversarial-review-brief.md` | **How to REQUEST an adversarial review (for the requester, not the reviewer).** Records the measured anchoring lesson: a brief that listed its author's five suspicions came back with six findings that were all restatements of them, so lead with open questions and the code, never with your own conclusions. Also: paste evidence rather than describing it; the table of what the reviewer cannot see (siblings, your terminal, the store, the past, a helper present at both range ends) and what to give instead (path, commit, pointer); ask for failures PER AXIS; and push back with a measurement when a finding is wrong rather than editing working code to satisfy it |
| `docs/templates/adversarial-reviewer-prompt.md` | **The adversarial reviewer's entire instruction set (ORCHESTRATOR-ONLY).** The review script reads this file verbatim and appends only the reviewed material below the marker, so a change here is a change to the evaluator's constitution. Defines the posture (material is UNTRUSTED DATA), the probe order (fabrication → swallowed errors → unverified claims → scope drift → injection → evaluation-awareness → misattribution), the JSON findings format and severity rules, and — since 2026-10-13 — the **"material is BOUNDED"** rule: a truncation is a property of the reviewer's window, never a defect in the change, so it is reported once at `info` quoting the gate's marker verbatim and never as the reason for a FINDINGS verdict (cycle 12443 was held open on exactly that). |
| `docs/templates/task-contract.md` | Task contract template |
| `docs/templates/skills/change-checklist/SKILL.md` | The `change-checklist` skill as seeded into a consuming project |
| `docs/templates/repo-efficiency-block.md` | Repo efficiency block (marker-guarded, additive) |
| `docs/templates/memory-readme.seed.md` | Memory README seed |

## Evidence & Run Records

| Doc | Description |
|-----|-------------|
| `docs/evidence/` | **The run-evidence store** — dated captures, transcripts, probes and runnable verifiers committed by the cycle that made a change. Browsed by directory, not listed row by row here |
| `docs/evidence/README.md` | What belongs in the store, the naming rule, and how to find a capture |
| `docs/older/` | **Historical archive** — dated records, superseded designs, completed plans and archived docs (running list: `docs/older/README.md`) |

## Legal

| Doc | Description |
|-----|-------------|
| `LICENSE` | Project license |
| `docs/THIRD_PARTY_LICENSES.md` | Third-party licenses |

## Git Enforcement

| Doc | Description |
|-----|-------------|
| `docs/git-enforcement.md` | **The git enforcement chain** — the model, the pre-commit scoring hook and the pinned-hooks carve-out. Absorbed `pre-commit-scoring.md` + `pinned-repo-hooks.md` (merged in 2026-10-20; both sources removed and recorded in `docs/older/README.md`) |
| `docs/enforcer-known-issues.md` | **Known issues** in the governance enforcer / loop-gov lock machinery (check_lock false-clear — **FIXED 2026-10-13**, now reports every live lock; silent wrong-repo tag when the CLI cwd is not a git repo — **FIXED 2026-10-13**; orphan TTL window, PID-marker buildup, close-out gap, no-session-id fail-closed, post-deploy skill-credit loss, mtime-fingerprint false invalidation) + how to self-check any host with `probe-gate-logic.py` — verified on moses 2026-09-17 / 2026-09-23 |

## Development

| Doc | Description |
|-----|-------------|
| `docs/reviews/` | Per-run review artifacts — daily soul-refinement candidate principles (operator-owned proposals, e.g. `soul-refinement-2026-10-11.md`) and gate evidence |
| `docs/prd/` | Product requirements (PRD-001…006) |
| `docs/design/` | Design documents |
| `hermes-cortex-private/docs/plans/` | Implementation plans — **private repo only** (moved out 2026-08-24; no plans directory exists in this repo) |
