# Skills Manifest — Hermes Cortex

Skills in this repo auto-install via `install.sh` step 10, which
recursively copies `skills/` to `~/.hermes/skills/`, preserving category
subdirectories. Skills are distributed across multiple categories matching
their domain.

> **AUTO-GENERATED FILE — do not edit by hand.** Regenerate with:
> `python3 ops/scripts/manage/gen-skills-manifest.py`
> The pre-commit doc audit runs `--check` whenever skills/ changes.


## App Store Optimization (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `app-store-optimization` | 1.0.0 | App Store Optimization (ASO) toolkit for researching keywords, analyzing competitor rankings, generating me... | `skill_view(name='app-store-optimization')` |

## Apple (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `macos-computer-use` | 1.0.0 | Drive the macOS desktop in the background — screenshots, mouse, keyboard, | `skill_view(name='macos-computer-use')` |
| `macos-service-management` | 1.0.0 | Manage and troubleshoot macOS launchd services — plist authoring, exit code diagnosis, variable expansion r... | `skill_view(name='macos-service-management')` |

## Autonomous Ai Agents (8 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `ai-coding-agents` | 1.0.0 | Delegate coding tasks to external AI coding agent CLIs — Claude Code, Codex CLI, and OpenCode. Orchestratio... | `skill_view(name='ai-coding-agents')` |
| `antigravity-cli` | 0.2.0 | Operate the Antigravity CLI (agy): plugins, auth, sandbox. | `skill_view(name='antigravity-cli')` |
| `blackbox` | 1.0.1 | Delegate coding tasks to the Blackbox AI multi-model CLI. | `skill_view(name='blackbox')` |
| `grok` | 0.1.1 | Delegate coding to xAI Grok Build CLI (features, PRs). | `skill_view(name='grok')` |
| `hermes-cortex` | 1.0.0 | Install, configure, and maintain Hermes Cortex — the observability and knowledge layer for Hermes Agent (Ol... | `skill_view(name='hermes-cortex')` |
| `hermes-cortex-setup` | 1.0.0 | Install and configure Hermes Cortex core components — Ollama, Bun, gbrain, health server, agent registry, h... | `skill_view(name='hermes-cortex-setup')` |
| `honcho` | 2.0.0 | Configure and troubleshoot Honcho memory for Hermes. | `skill_view(name='honcho')` |
| `openhands` | 0.1.0 | Delegate coding to OpenHands CLI (model-agnostic, LiteLLM). | `skill_view(name='openhands')` |

## Blockchain (3 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `evm` | 1.0.0 | Read-only EVM client: wallets, tokens, gas across 8 chains. | `skill_view(name='evm')` |
| `hyperliquid` | 0.1.0 | Hyperliquid market data, account history, trade review. | `skill_view(name='hyperliquid')` |
| `solana` | 0.2.0 | Query Solana wallets, tokens, txs, and NFTs in USD. | `skill_view(name='solana')` |

## Brand Guidelines (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `brand-guidelines` | 1.0.0 | When the user wants to apply, document, or enforce brand guidelines for any product or company. Also use wh... | `skill_view(name='brand-guidelines')` |

## Campaign Analytics (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `campaign-analytics` | 1.0.0 | Analyzes campaign performance with multi-touch attribution, funnel conversion analysis, and ROI calculation... | `skill_view(name='campaign-analytics')` |

## Cold Email (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `cold-email` | 1.0.0 | Write B2B cold emails and follow-up sequences that get replies. Use when the user wants to write cold outre... | `skill_view(name='cold-email')` |

## Communication (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `one-three-one-rule` | 1.0.0 | Structured decision-making framework for technical proposals and trade-off analysis. When the user faces a... | `skill_view(name='one-three-one-rule')` |

## Content Creator (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `content-creator` | 1.0.0 | Deprecated redirect skill that routes legacy 'content creator' requests to the correct specialist. Use when... | `skill_view(name='content-creator')` |

## Content Humanizer (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `content-humanizer` | 1.0.0 | Makes AI-generated content sound genuinely human — not just cleaned up, but alive. Use when content feels r... | `skill_view(name='content-humanizer')` |

## Content Production (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `content-production` | 1.0.0 | Full content production pipeline — takes a topic from blank page to published-ready piece. Use when you nee... | `skill_view(name='content-production')` |

## Content Strategy (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `content-strategy` | 1.0.0 | When the user wants to plan a content strategy, decide what content to create, or figure out what topics to... | `skill_view(name='content-strategy')` |

## Copywriting (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `copywriting` | 1.0.0 | When the user wants to write, rewrite, or improve marketing copy for any page — including homepage, landing... | `skill_view(name='copywriting')` |

## Creative (10 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `agent-identity` | 1.0.0 | Design, author, and iterate an agent's identity/persona — the SOUL.md | `skill_view(name='agent-identity')` |
| `baoyu-article-illustrator` | 1.57.0 | Article illustrations: type × style × palette consistency. | `skill_view(name='baoyu-article-illustrator')` |
| `baoyu-comic` | 1.56.1 | Knowledge comics (知识漫画): educational, biography, tutorial. | `skill_view(name='baoyu-comic')` |
| `blender-mcp` | 2.1.0 | Drive Blender via the catalog blender MCP, with bpy recipes. | `skill_view(name='blender-mcp')` |
| `concept-diagrams` | 0.1.0 | Generate flat, minimal educational SVG visuals as HTML. | `skill_view(name='concept-diagrams')` |
| `creative-ideation` | 2.1.0 | Generate ideas via named methods from creative practice. | `skill_view(name='creative-ideation')` |
| `hyperframes` | 1.0.0 | Render MP4/WebM videos from HTML compositions. | `skill_view(name='hyperframes')` |
| `kanban-video-orchestrator` | 1.0.0 | Plan and run multi-agent video production pipelines. | `skill_view(name='kanban-video-orchestrator')` |
| `meme-generation` | 2.0.0 | Create meme PNGs from templates with Pillow text overlay. | `skill_view(name='meme-generation')` |
| `pixel-art` | 2.0.0 | Pixel art w/ era palettes (NES, Game Boy, PICO-8). | `skill_view(name='pixel-art')` |

## Devops (105 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `admin-cli-tools` | 1.0.0 | Patterns and architecture for admin-level CLI tools that use direct DB access, not agent-level API auth. | `skill_view(name='admin-cli-tools')` |
| `agent-collector-troubleshoot` | 1.0.0 | Use when collectors can't send. Diagnoses bus, paths, crons. | `skill_view(name='agent-collector-troubleshoot')` |
| `agent-fundamentals` | 1.0.0 | Universal 'basic things every agent should know' — distilled from real frustration patterns across 10+ sess... | `skill_view(name='agent-fundamentals')` |
| `agent-health-monitoring` | 3.5.0 | Cross-server agent health monitoring using binary status vectors — deploy health endpoints on each agent, p... | `skill_view(name='agent-health-monitoring')` |
| `arq-worker-startup-pitfalls` | 1.0.0 | Use when an arq worker crash-loops or runs no jobs. | `skill_view(name='arq-worker-startup-pitfalls')` |
| `auto-remediation` | 1.0.0 | Auto-remediate cron job failures, agent inbox requests, and service issues. Checks every 5m and fixes known... | `skill_view(name='auto-remediation')` |
| `auto-remediation-ecosystem` | 1.0.0 | Complete auto-remediation ecosystem setup, configuration, and maintenance | `skill_view(name='auto-remediation-ecosystem')` |
| `auto-remediation-setup` | 1.0.0 | Set up, configure, and troubleshoot the auto-remediation system. | `skill_view(name='auto-remediation-setup')` |
| `bus-connectivity-diagnostics` | 1.0.0 | Diagnostic procedures for Agent Bus connectivity, permissions, and message delivery. Covers the three bus p... | `skill_view(name='bus-connectivity-diagnostics')` |
| `bus-inbox-check` | 1.0.0 | Check agent bus inbox depth and read messages via HTTP API — for use in LLM cron context where inbox_read M... | `skill_view(name='bus-inbox-check')` |
| `bus-queue-maintenance` | 1.0.0 | Bus queue lifecycle — inspecting stuck messages, archiving orphaned messages, navigating state constraints,... | `skill_view(name='bus-queue-maintenance')` |
| `ci-cd-pipeline` | 1.0.0 | CI/CD pipeline configuration patterns: GitHub Actions, multi-stage builds, testing matrices, deployment wor... | `skill_view(name='ci-cd-pipeline')` |
| `cleanup-commit-regression-check` | 1.0.0 | When scripts fail with NameError after a mass-edit commit. | `skill_view(name='cleanup-commit-regression-check')` |
| `codebase-portability` | 1.0.0 | Systematically find and fix hardcoded absolute paths across scripts, docs, and configs. Ensures codebases w... | `skill_view(name='codebase-portability')` |
| `config-drift-diagnostics` | 1.0.0 | Container configs stale? Compare vs source in 3 locations. | `skill_view(name='config-drift-diagnostics')` |
| `cortex-bus` | 1.2.0 | Agent Bus (PGMQ) operations — queue inspection, DLQ management, message recovery, auth, and health diagnost... | `skill_view(name='cortex-bus')` |
| `cortex-bus-automation` | 2.0.0 | Automated Agent Bus processing via MCP. | `skill_view(name='cortex-bus-automation')` |
| `cortex-bus-inbox` | 2.0.0 | MCP inbox tools for cortex-bus messaging. | `skill_view(name='cortex-bus-inbox')` |
| `cortex-bus-messaging` | 1.2.0 | ORCHESTRATORS ONLY — message the orchestrator via the bus MCP client (inbox_send). Workers use contact-orch... | `skill_view(name='cortex-bus-messaging')` |
| `cortex-bus-polling` | 2.0.0 | Agent Bus polling setup — MCP tools, cron, verification. | `skill_view(name='cortex-bus-polling')` |
| `cortex-deployment-sync` | 1.0.0 | Use when pulling latest or running cortex update. | `skill_view(name='cortex-deployment-sync')` |
| `cortex-preflight` | 1.0.0 | Hermes Cortex supporting pre-flight checks — supplements Hermes default survey-before-action with repo-spec... | `skill_view(name='cortex-preflight')` |
| `cron-cost-tracking` | 1.0.0 | SQLite-backed per-run token usage and cost tracking for Hermes cron jobs. Deploys cost_store.py and patches... | `skill_view(name='cron-cost-tracking')` |
| `cron-format-standard` | 3.0.0 | Standard three-phase output format for ALL LLM-driven cron jobs. Uses concrete examples — not annotated pla... | `skill_view(name='cron-format-standard')` |
| `cron-job-management` | 1.0.0 | Create, name, list, and maintain Hermes cron jobs — no_agent watchdog scripts, naming conventions, and the... | `skill_view(name='cron-job-management')` |
| `cron-no-agent-conversion` | 1.0.0 | Convert LLM-driven Hermes agent crons to no_agent scripts with targeted API calls. Maximizes deterministic... | `skill_view(name='cron-no-agent-conversion')` |
| `cron-quality-gate` | 1.0.0 | Prevents LLM cron jobs from delivering garbage with a self-check quality gate and automated watchdog. | `skill_view(name='cron-quality-gate')` |
| `cron-request-protocol` | 1.3.0 | Protocol for non-orchestrator agents to request cron job creation, updates, or removal via the agent inbox.... | `skill_view(name='cron-request-protocol')` |
| `cross-agent-design` | 1.0.0 | Before designing any cross-agent feature, protocol, or workflow: trace the receiving agent's end-to-end con... | `skill_view(name='cross-agent-design')` |
| `cross-repo-sync` | 1.0.0 | Update the same file (config, docs, boilerplate) across multiple project repos in a single coordinated pass... | `skill_view(name='cross-repo-sync')` |
| `daily-bible-reading` | 1.0.0 | Daily cron job that reads one book of the Bible, extracts 3 lessons with practical application to server op... | `skill_view(name='daily-bible-reading')` |
| `deployed-component-verification` | 1.1.0 | Verify deployed components match their repo source — detect stale copies, validate symlinks, and ensure the... | `skill_view(name='deployed-component-verification')` |
| `doc-freshness` | 1.1.0 | Ensure AGENTS.md and SOUL.md stay current across all agents and projects. Weekly audit, post-update broadca... | `skill_view(name='doc-freshness')` |
| `docker-management` | 1.0.0 | Manage Docker containers, images, volumes, and Compose. | `skill_view(name='docker-management')` |
| `documentation-scope` | 1.0.0 | Multi-audience documentation scoping conventions for Hermes Cortex. Defines when and how to distinguish gen... | `skill_view(name='documentation-scope')` |
| `enforcement-change-safety` | 1.0.0 | Use before enforcement code changes or shared-repo commits. | `skill_view(name='enforcement-change-safety')` |
| `enforcer-modification-considerations` | 1.0.0 | Use before modifying any enforcer/governance code. | `skill_view(name='enforcer-modification-considerations')` |
| `env-aware-compose-wrapper` | 2 | Build an env-aware `_compose()` wrapper for `./run` CLI scripts that requires an explicit environment varia... | `skill_view(name='env-aware-compose-wrapper')` |
| `eval-harness` | 1.0.0 | Systematic evaluation framework for agent capabilities — capability tests, regression suites, failure analysis | `skill_view(name='eval-harness')` |
| `file-ownership-boundaries` | 1.0.0 | Know which files are yours to modify vs Hermes defaults. Covers the two-domain split (Hermes Agent vs herme... | `skill_view(name='file-ownership-boundaries')` |
| `fix-without-asking` | 1.2.0 | When you discover an issue mid-task, the correct response is begin_change — not a question. | `skill_view(name='fix-without-asking')` |
| `fleet-commands` | 1.6.0 | Send operational commands to fleet agents via the PGMQ bus — message format, delivery verification, bus_acc... | `skill_view(name='fleet-commands')` |
| `fleet-management` | 1.0.0 | Fleet-level agent management for Hermes Cortex — agent registry, fleet ready score, fleet-audit CLI, adding... | `skill_view(name='fleet-management')` |
| `fresh-tomato-router` | 1.0.0 | Interact with FreshTomato/DD-WRT routers programmatically via curl — authentication, nvram access, port for... | `skill_view(name='fresh-tomato-router')` |
| `git-deployment-workflow` | 1.0.0 | Deploy code by pushing to bare remote repositories (Capistrano-style deployment targets). Covers force push... | `skill_view(name='git-deployment-workflow')` |
| `git-forensics` | 1.0.0 | Use when files vanished or uncommitted deletions appeared. | `skill_view(name='git-forensics')` |
| `golden-parity-harness` | 1.0.0 | Golden known-answer parity testing for system replacement. | `skill_view(name='golden-parity-harness')` |
| `governance-compliance-reporting` | 1.0.0 | Review agent commits for enforcement compliance. | `skill_view(name='governance-compliance-reporting')` |
| `governance-identity-hardening` | 1.0.0 | Use when hardening orchestrator identity or unlock tokens. | `skill_view(name='governance-identity-hardening')` |
| `governance-sentinel` | 1.0.0 | Recurring governance introspection — scrape brain sync snapshots for codepath patterns, compile weekly insi... | `skill_view(name='governance-sentinel')` |
| `health-external-verification` | 1.0.0 | Verify your health endpoint is externally reachable by testing the URL end-to-end instead of assuming local... | `skill_view(name='health-external-verification')` |
| `hermes-backup` | 1.0.0 | Use when performing a full-system backup of a Hermes Agent server — survey, clean up caches, checkpoint dat... | `skill_view(name='hermes-backup')` |
| `hermes-cortex-maintenance` | 1.36.0 | Maintain an installed Hermes Cortex instance — update both the upstream Hermes Agent and the cortex repo la... | `skill_view(name='hermes-cortex-maintenance')` |
| `hermes-gateway-operations` | 1.0.0 | Diagnose, configure, and maintain Hermes messaging gateway platforms (Telegram, Discord, WhatsApp, etc.). C... | `skill_view(name='hermes-gateway-operations')` |
| `hermes-home-cleanup` | 1.0.0 | Use when cleaning ~/.hermes or ~/.hermes-cortex. Verify. | `skill_view(name='hermes-home-cleanup')` |
| `hermes-recovery` | 1.0.0 | Server migration, disaster recovery, and restoration workflows for Hermes Agent — restoring from tar.gz arc... | `skill_view(name='hermes-recovery')` |
| `hermes-s6-container-supervision` | 1.0.0 | Modify or debug s6 services in the Hermes Docker image. | `skill_view(name='hermes-s6-container-supervision')` |
| `inbox-remediation` | 1.1.0 | Auto-remediate hermes-cortex issues reported by peer agents via the Agent Bus. Scans pending remediation ma... | `skill_view(name='inbox-remediation')` |
| `inference-sh-cli` | 1.0.0 | Run 150+ AI apps (image, video, LLM) via inference.sh CLI. | `skill_view(name='inference-sh-cli')` |
| `integration-audit` | 1.0.0 | Comprehensive integration audit — runs all changed subsystems together before final commit to catch cross-s... | `skill_view(name='integration-audit')` |
| `kanban-orchestrator` | 3.0.0 | Decomposition playbook + anti-temptation rules for an orchestrator profile routing work through Kanban. The... | `skill_view(name='kanban-orchestrator')` |
| `kanban-worker` | 2.0.0 | Pitfalls, examples, and edge cases for Hermes Kanban workers. The lifecycle itself is auto-injected into ev... | `skill_view(name='kanban-worker')` |
| `langfuse-observability` | 1.0.0 | Wire a self-hosted Langfuse instance to Hermes Agent — generate API keys, configure env vars, enable the bu... | `skill_view(name='langfuse-observability')` |
| `langfuse-self-hosted` | 1.0.0 | Deploy, configure, and wire Langfuse v3 with ClickHouse for LLM observability — Docker compose, SIGSEGV-saf... | `skill_view(name='langfuse-self-hosted')` |
| `linux-performance-diagnostics` | 1.0.0 | Systematic "system is slow" diagnosis — baseline resource check, CPU frequency scaling analysis, process/co... | `skill_view(name='linux-performance-diagnostics')` |
| `linux-server-hardening` | 1.0.0 | Systematic Linux server hardening with tiered prioritization. Covers UFW firewall, SSH hardening (key-only... | `skill_view(name='linux-server-hardening')` |
| `llm-judge-scorer` | 1.0.0 | LLM-as-Judge trace quality scorer. Evaluates Hermes conversation traces in Langfuse using a local Ollama mo... | `skill_view(name='llm-judge-scorer')` |
| `local-config-drift-diagnostics` | 1.0.0 | Container configs stale? Compare vs source in 3 locations. | `skill_view(name='local-config-drift-diagnostics')` |
| `local-pipeline-debugging` | 1.0.0 | Check the data store and service logs before changing code. | `skill_view(name='local-pipeline-debugging')` |
| `loop-governance` | 1.5.0 | TDD cycle scoring, self-improvement, and governance system for Hermes Cortex. Scores completeness/quality/p... | `skill_view(name='loop-governance')` |
| `maintenance-scan` | 1.0.0 | Systematic system health survey run proactively when the user gives an open-ended directive to "find work"... | `skill_view(name='maintenance-scan')` |
| `moses-inbox-remediation` | 1.0.0 | Auto-remediate hermes-cortex issues reported by peer agents via the agent inbox. Scans pending remediation... | `skill_view(name='moses-inbox-remediation')` |
| `mycortex` | 1.1.0 | Use for mycortex knowledge brain work or gbrain migration. | `skill_view(name='mycortex')` |
| `name-discovery` | 1.0.0 | Use when checking if a software/tool name is available for use — searches GitHub, web, and registries for c... | `skill_view(name='name-discovery')` |
| `nextjs-docker-multistage` | 1.0.0 | Next.js Docker multi-stage builds with standalone output — minimal runtime images, no node_modules in produ... | `skill_view(name='nextjs-docker-multistage')` |
| `nginx-security-pipeline` | 1.0.0 | Set up nginx security with IP blocking, fail2ban integration, daily automated scanning, and atomic deploy.... | `skill_view(name='nginx-security-pipeline')` |
| `nginx-web-app-deployment` | 1.0.0 | Deploy a custom web app (Flask, Python, Node) behind nginx — upstream config, SSL, basic auth, rate limitin... | `skill_view(name='nginx-web-app-deployment')` |
| `offline-code` | 1.0.0 | Offline code snippet search + generation using local Ollama models. Search a 518-snippet corpus across 32 c... | `skill_view(name='offline-code')` |
| `orch-skill-lifecycle` | 1.0.0 | Unified daily skill lifecycle pipeline — collects lessons, evaluates quality, and upgrades skills/SOUL.md.... | `skill_view(name='orch-skill-lifecycle')` |
| `orch-weekly-auto-fix` | 1.1.0 | After the weekly opportunity scan identifies issues, run auto-fix patterns — git pull, branch cleanup, Dock... | `skill_view(name='orch-weekly-auto-fix')` |
| `package-security` | 1.0.0 | Age-gated package installation protection. Before installing any package with pip, npm, brew, or cargo, ver... | `skill_view(name='package-security')` |
| `pinggy-tunnel` | 0.1.0 | Zero-install localhost tunnels over SSH via Pinggy. | `skill_view(name='pinggy-tunnel')` |
| `pipeline-debugging` | 1.0.0 | Check the data store and service logs before changing code. | `skill_view(name='pipeline-debugging')` |
| `postgres-docker` | 1.0.0 | Tune and configure PostgreSQL running inside Docker containers — custom configs, mounts, command overrides,... | `skill_view(name='postgres-docker')` |
| `prevent-crash-looping` | 1.0.0 | How to prevent systemd service crash-looping from port conflicts, missing directories, and failed dependencies | `skill_view(name='prevent-crash-looping')` |
| `proactive-system-scan` | 1.0.0 | Multi-faceted system scan to discover work, issues, and improvement opportunities when the user gives an op... | `skill_view(name='proactive-system-scan')` |
| `project-run-scripts` | 1.0.0 | DEFINITIVE canonical template for ./run — single bash CLI entrypoint covering Docker lifecycle, dev servers... | `skill_view(name='project-run-scripts')` |
| `remediation-investigation` | 1.0.0 | Trace remediation sensor reports to their source, cross-reference live state, and distinguish transient fro... | `skill_view(name='remediation-investigation')` |
| `repo-health-review` | 1.1.0 | Systematic repo health review — survey scripts, detect duplicates, check naming, find gaps, prune dead weig... | `skill_view(name='repo-health-review')` |
| `security-audit` | 2.3.0 | Full-pipeline Ubuntu/Debian server security + cleanup. Audits DDoS protection, anti-spam, system hardening,... | `skill_view(name='security-audit')` |
| `self-improvement-pipeline` | 1.0.0 | Transform user corrections and system warnings into permanent guardrails. Covers zero-ask discipline, docto... | `skill_view(name='self-improvement-pipeline')` |
| `sensor-false-positive-remediation` | 1.0.0 | Handle false positives from the auto-remediation sensor pipeline. Covers the trace-before-create workflow f... | `skill_view(name='sensor-false-positive-remediation')` |
| `server-administration` | 1.10.0 | Ongoing IT & Security Administration for production Linux servers. Covers routine health checks, Docker con... | `skill_view(name='server-administration')` |
| `server-hardening` | 1.8.0 | Comprehensive security audit and hardening for Linux servers running web services (nginx, Docker, fail2ban,... | `skill_view(name='server-hardening')` |
| `session-start-discipline` | 1.1.0 | Restore cross-session todos, enforce skill-loading discipline at session start | `skill_view(name='session-start-discipline')` |
| `shell-scripting` | 1.1.0 | Shell scripting patterns, portability pitfalls, and cross-platform compatibility for bash/awk scripts in th... | `skill_view(name='shell-scripting')` |
| `skill-curation` | 1.0.0 | Consolidate, dedupe, and prune the skill library — merge overlapping skills into one (absorbed_into), delet... | `skill_view(name='skill-curation')` |
| `staging-server-operations` | 1.19.0 | Safe operational practices for Docker-based staging servers — volume management, change verification, and d... | `skill_view(name='staging-server-operations')` |
| `sync-allow-ips-to-fail2ban` | 1.0.0 | Sync IPs from allow-ips-manual.conf to fail2ban ignoreip | `skill_view(name='sync-allow-ips-to-fail2ban')` |
| `telegram-delivery-diagnostics` | 1.0.0 | Diagnose and fix Telegram delivery issues for Hermes cron jobs — delivery pipeline tracing, DNS/network dia... | `skill_view(name='telegram-delivery-diagnostics')` |
| `third-party-code-vetting` | 1.0.0 | Vet third-party code before it enters the repo or runs on a host — upstream patches, vendored scripts, inst... | `skill_view(name='third-party-code-vetting')` |
| `todo-persistence` | 1.0.0 | Cross-session todo persistence using the shared gbrain Postgres DB. Covers the bus.todos table, todo-db.py... | `skill_view(name='todo-persistence')` |
| `two-hard-rules` | 1.0.0 | Two hard rules every agent must follow: USE LOOP GOVERNANCE ALWAYS. SHARE IMPROVEMENTS TO THE PUBLIC REPO. | `skill_view(name='two-hard-rules')` |
| `unified-cli-script` | 1.0.0 | Design a unified ./run CLI script for multi-environment Docker Compose deployments. Covers the _compose() w... | `skill_view(name='unified-cli-script')` |
| `watchers` | 1.0.0 | Poll RSS, JSON APIs, and GitHub with watermark dedup. | `skill_view(name='watchers')` |

## Dogfood (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `adversarial-ux-test` | 1.0.0 | Roleplay a hostile user to find and triage UX pain points. | `skill_view(name='adversarial-ux-test')` |

## Email (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `agentmail` | 1.0.0 | Give the agent its own inbox: send and receive email. | `skill_view(name='agentmail')` |

## Email Sequence (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `email-sequence` | 1.0.0 | Write a multi-email nurture/onboarding/launch sequence with a goal per email. Use when asked to write an em... | `skill_view(name='email-sequence')` |

## Finance (8 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `3-statement-model` | 1.0.0 | Build integrated IS/BS/CF financial workbooks in Excel. | `skill_view(name='3-statement-model')` |
| `comps-analysis` | 1.0.0 | Build comparable-company valuation workbooks in Excel. | `skill_view(name='comps-analysis')` |
| `dcf-model` | 1.0.0 | Build discounted cash flow valuation workbooks in Excel. | `skill_view(name='dcf-model')` |
| `excel-author` | 1.0.0 | Build auditable financial workbooks headless via openpyxl. | `skill_view(name='excel-author')` |
| `lbo-model` | 1.0.0 | Build leveraged buyout workbooks with IRR/MOIC in Excel. | `skill_view(name='lbo-model')` |
| `merger-model` | 1.0.0 | Build M&A accretion/dilution workbooks in Excel. | `skill_view(name='merger-model')` |
| `pptx-author` | 1.0.0 | Build PowerPoint decks headless with python-pptx. | `skill_view(name='pptx-author')` |
| `stocks` | 0.1.0 | Stock quotes, history, search, compare, crypto via Yahoo. | `skill_view(name='stocks')` |

## Gaming (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `minecraft-modpack-server` | 1.0.0 | Host modded Minecraft servers (CurseForge, Modrinth). | `skill_view(name='minecraft-modpack-server')` |
| `pokemon-player` | 1.0.0 | Play Pokemon via headless emulator + RAM reads. | `skill_view(name='pokemon-player')` |

## GitHub (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `commit-message` | 1.0.0 | Write clear, structured git commit messages following Conventional Commits format. Includes type prefixes,... | `skill_view(name='commit-message')` |
| `pr-review` | 1.0.0 | Full PR review pipeline — whole-repo context, architecture analysis, lesson-DB pattern matching, test regre... | `skill_view(name='pr-review')` |

## Health (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `fitness-nutrition` | 1.0.0 | Gym workout planner and nutrition tracker. Search 690+ exercises by muscle, equipment, or category via wger... | `skill_view(name='fitness-nutrition')` |
| `neuroskill-bci` | 1.0.0 | Connect to a running NeuroSkill instance and incorporate the user's real-time cognitive and emotional state... | `skill_view(name='neuroskill-bci')` |

## Hermes Agent (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `skill-miner` | 1.0.0 | Mine loop governance DB, sessions, and memory for reusable skill patterns. Scores findings with nomic-embed... | `skill_view(name='skill-miner')` |
| `soul-refinement` | 1.0.0 | Daily SOUL.md refinement process — mine sessions for lessons, apply corrections, codify principles. Optiona... | `skill_view(name='soul-refinement')` |

## Hermes Desktop Plugins (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `hermes-desktop-plugins` | 1.0.0 | Write desktop app plugins that add UI panes and commands. | `skill_view(name='hermes-desktop-plugins')` |

## Hermes Themes (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `hermes-themes` | 1.0.0 | Author a Hermes color theme that skins every surface. | `skill_view(name='hermes-themes')` |

## Launch Strategy (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `launch-strategy` | 1.0.0 | When the user wants to plan a product launch, feature announcement, or release strategy. Also use when the... | `skill_view(name='launch-strategy')` |

## Marketing Psychology (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `marketing-psychology` | 1.0.0 | When the user wants to apply psychological principles, mental models, or behavioral science to marketing. A... | `skill_view(name='marketing-psychology')` |

## Marketing Strategy Pmm (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `marketing-strategy-pmm` | 1.0.0 | Product marketing skill for positioning, GTM strategy, competitive intelligence, and product launches. Use... | `skill_view(name='marketing-strategy-pmm')` |

## Mcp (2 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `fastmcp` | 1.0.0 | Build, test, and deploy Python MCP servers. | `skill_view(name='fastmcp')` |
| `mcporter` | 1.0.0 | List, auth, and call MCP servers/tools from the terminal. | `skill_view(name='mcporter')` |

## Migration (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `openclaw-migration` | 1.0.0 | Import an OpenClaw setup (memories, skills) into Hermes. | `skill_view(name='openclaw-migration')` |

## Mlops (30 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `axolotl` | 1.0.0 | Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO). | `skill_view(name='axolotl')` |
| `chroma` | 1.0.0 | Embedding database for RAG and semantic search. | `skill_view(name='chroma')` |
| `clip` | 1.0.0 | Zero-shot image classification and image-text search. | `skill_view(name='clip')` |
| `distributed-llm-pretraining-torchtitan` | 1.0.1 | Pretrain LLMs at scale with PyTorch 4D parallelism. | `skill_view(name='distributed-llm-pretraining-torchtitan')` |
| `dspy` | 1.0.0 | DSPy: declarative LM programs, auto-optimize prompts, RAG. | `skill_view(name='dspy')` |
| `faiss` | 1.0.0 | Fast vector similarity search at billion scale. | `skill_view(name='faiss')` |
| `fine-tuning-with-trl` | 1.0.1 | TRL: SFT, DPO, GRPO, RLOO reward modeling for LLM RLHF. | `skill_view(name='fine-tuning-with-trl')` |
| `guidance` | 1.0.1 | Constrain LLM output with grammars; guarantee valid JSON. | `skill_view(name='guidance')` |
| `huggingface-accelerate` | 1.0.1 | Run PyTorch training across GPUs with minimal changes. | `skill_view(name='huggingface-accelerate')` |
| `instructor` | 1.0.0 | Structured LLM outputs validated with Pydantic. | `skill_view(name='instructor')` |
| `lambda-labs-gpu-cloud` | 1.0.0 | On-demand GPU cloud instances for ML training. | `skill_view(name='lambda-labs-gpu-cloud')` |
| `llava` | 1.0.0 | Vision-language chat: VQA, captioning, image dialogue. | `skill_view(name='llava')` |
| `modal-serverless-gpu` | 1.0.1 | Serverless GPU cloud for ML jobs and model APIs. | `skill_view(name='modal-serverless-gpu')` |
| `nemo-curator` | 1.0.1 | Curate LLM training data: dedupe, filter, PII redaction. | `skill_view(name='nemo-curator')` |
| `obliteratus` | 2.0.0 | OBLITERATUS: abliterate LLM refusals (diff-in-means). | `skill_view(name='obliteratus')` |
| `ollama-setup` | 1.1.0 | Install, configure, and manage Ollama on Linux — including sudo-free tarball install, user systemd service,... | `skill_view(name='ollama-setup')` |
| `optimizing-attention-flash` | 1.0.1 | Speed up long-sequence transformer training and inference. | `skill_view(name='optimizing-attention-flash')` |
| `outlines` | 1.0.1 | Outlines: structured JSON/regex/Pydantic LLM generation. | `skill_view(name='outlines')` |
| `peft-fine-tuning` | 1.0.0 | Fine-tune large LLMs with LoRA on limited GPU memory. | `skill_view(name='peft-fine-tuning')` |
| `pinecone` | 1.0.1 | Managed vector DB for production RAG and search. | `skill_view(name='pinecone')` |
| `pytorch-fsdp` | 1.0.0 | Fully sharded data-parallel training for large models. | `skill_view(name='pytorch-fsdp')` |
| `pytorch-lightning` | 1.0.0 | Clean training loops with built-in distributed support. | `skill_view(name='pytorch-lightning')` |
| `qdrant-vector-search` | 1.0.1 | Vector search engine for production RAG systems. | `skill_view(name='qdrant-vector-search')` |
| `simpo-training` | 1.0.0 | Reference-free preference alignment, simpler than DPO. | `skill_view(name='simpo-training')` |
| `slime-rl-training` | 1.0.0 | RL post-training for LLMs with Megatron and SGLang. | `skill_view(name='slime-rl-training')` |
| `sparse-autoencoder-training` | 1.0.1 | Train sparse autoencoders to interpret model features. | `skill_view(name='sparse-autoencoder-training')` |
| `stable-diffusion-image-generation` | 1.0.0 | Text-to-image generation, inpainting, and img2img. | `skill_view(name='stable-diffusion-image-generation')` |
| `tensorrt-llm` | 1.0.1 | High-throughput LLM inference on NVIDIA GPUs. | `skill_view(name='tensorrt-llm')` |
| `unsloth` | 1.0.0 | Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM. | `skill_view(name='unsloth')` |
| `whisper` | 1.0.0 | Transcribe and translate speech in 99 languages. | `skill_view(name='whisper')` |

## Paid Ads (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `paid-ads` | 1.0.0 | When the user wants help with paid advertising campaigns on Google Ads, Meta (Facebook/Instagram), LinkedIn... | `skill_view(name='paid-ads')` |

## Productivity (8 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `canvas` | 1.0.0 | Fetch Canvas LMS courses and assignments via API token. | `skill_view(name='canvas')` |
| `here.now` | 1.15.3 | Publish sites to {slug}.here.now and store files in Drives. | `skill_view(name='here.now')` |
| `korean-language-learning` | 1.0.0 | A warm, practical Korean language companion for English speakers aged 50+. Covers Hangul mastery, essential... | `skill_view(name='korean-language-learning')` |
| `memento-flashcards` | 1.0.0 | Spaced-repetition flashcard system. Create cards from facts or text, chat with flashcards using free-text a... | `skill_view(name='memento-flashcards')` |
| `shop-app` | 0.0.28 | Shop.app: product search, order tracking, returns, reorder. | `skill_view(name='shop-app')` |
| `shopify` | 1.0.0 | Shopify Admin & Storefront GraphQL APIs via curl. Products, orders, customers, inventory, metafields. | `skill_view(name='shopify')` |
| `siyuan` | 1.0.0 | Query and edit a SiYuan knowledge base via its API. | `skill_view(name='siyuan')` |
| `telephony` | 1.0.0 | Provision Twilio numbers, SMS/MMS, and AI outbound calls. | `skill_view(name='telephony')` |

## Programmatic Seo (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `programmatic-seo` | 1.0.0 | When the user wants to create SEO-driven pages at scale using templates and data. Also use when the user me... | `skill_view(name='programmatic-seo')` |

## Red Teaming (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `godmode` | 1.0.0 | Jailbreak LLMs: Parseltongue, GODMODE, ULTRAPLINIAN. | `skill_view(name='godmode')` |

## Research (13 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `bioinformatics` | 1.0.0 | Gateway to 400+ genomics and computational biology skills. | `skill_view(name='bioinformatics')` |
| `brand-intelligence` | 1.0.0 | Monitor and analyze brand mentions, sentiment, share of voice, and competitive positioning across web/socia... | `skill_view(name='brand-intelligence')` |
| `darwinian-evolver` | 0.1.0 | Evolve prompts/regex/SQL/code with Imbue's evolution loop. | `skill_view(name='darwinian-evolver')` |
| `domain-intel` | 1.0.0 | Passive recon of subdomains, SSL certs, WHOIS, and DNS. | `skill_view(name='domain-intel')` |
| `drug-discovery` | 1.0.0 | Pharmaceutical research assistant for drug discovery workflows. Search bioactive compounds on ChEMBL, calcu... | `skill_view(name='drug-discovery')` |
| `duckduckgo-search` | 1.3.0 | Free keyless web, news, and image search via ddgs. | `skill_view(name='duckduckgo-search')` |
| `gitnexus-explorer` | 1.0.0 | Serve an interactive codebase knowledge graph web UI. | `skill_view(name='gitnexus-explorer')` |
| `osint-investigation` | 0.1.0 | Follow the money via public records and sanctions data. | `skill_view(name='osint-investigation')` |
| `parallel-cli` | 1.1.0 | Agent-native web search, deep research, and enrichment. | `skill_view(name='parallel-cli')` |
| `qmd` | 1.0.0 | Hybrid local search over notes, docs, and transcripts. | `skill_view(name='qmd')` |
| `recurring-reports` | 1.0.0 | Design and run recurring automated reports: define cadence, metrics, sources, and delivery; wire to cron; v... | `skill_view(name='recurring-reports')` |
| `scrapling` | 1.0.0 | Scrape sites with stealth browsing and Cloudflare bypass. | `skill_view(name='scrapling')` |
| `searxng-search` | 1.0.1 | Free keyless meta-search aggregating 70+ engines. | `skill_view(name='searxng-search')` |

## Schema Markup (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `schema-markup` | 1.0.0 | Add, fix, or optimize schema markup and structured data. Use when the user mentions schema markup, structur... | `skill_view(name='schema-markup')` |

## Security (8 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `1password` | 1.0.0 | Set up op CLI, sign in, and read or inject secrets. | `skill_view(name='1password')` |
| `credential-leak-response` | 1.0.0 | Use when a credential leaks — verify live, scrub, rotate. | `skill_view(name='credential-leak-response')` |
| `oss-forensics` | 1.0.0 | Supply chain investigation, evidence recovery, and forensic analysis for GitHub repositories. | `skill_view(name='oss-forensics')` |
| `pii-scrubbing` | 1.0.0 | Systematically scrub Personally Identifiable Information (PII) from a codebase — inventory real domains, ho... | `skill_view(name='pii-scrubbing')` |
| `secure-credential-handling` | 1.0.0 | Handle passwords, API keys, tokens, and secrets securely when using terminal/read_file/execute_code tools —... | `skill_view(name='secure-credential-handling')` |
| `sherlock` | 1.0.0 | Find accounts for a username across 400+ platforms. | `skill_view(name='sherlock')` |
| `threat-defense-pipeline` | 1.0.0 | Layered defense system: fail2ban jails + nginx IP blocking + daily auto-deploy pipeline. How to add blocked... | `skill_view(name='threat-defense-pipeline')` |
| `web-pentest` | 1.0.0 | Authorized web application penetration testing — reconnaissance, vulnerability | `skill_view(name='web-pentest')` |

## Seo Audit (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `seo-audit` | 1.0.0 | Use when the user wants to audit, review, or diagnose SEO issues on a site: rankings, technical SEO, on-pag... | `skill_view(name='seo-audit')` |

## Skill Vetting (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `skill-vetting` | 1.0.0 | Vet skills for safety, external dependencies, and self-contained operation before installing. Scan scripts,... | `skill_view(name='skill-vetting')` |

## Social Content (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `social-content` | 1.0.0 | When the user wants help creating, scheduling, or optimizing social media content for LinkedIn, Twitter/X,... | `skill_view(name='social-content')` |

## Social Media (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `client-brand-brand-marketing` | 1.0.0 | Full brand marketing skill for The Client Brand (@client-brand.co) — sustainable fashion bags by Korean-American founders Amy... | `skill_view(name='client-brand-brand-marketing')` |

## Social Media Analyzer (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `social-media-analyzer` | 1.0.0 | Social media campaign analysis and performance tracking. Calculates engagement rates, ROI, and benchmarks a... | `skill_view(name='social-media-analyzer')` |

## Software Development (47 skills)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `adversarial-verifier` | 1.0.0 | Adversarial verification — systematically attempts to break code BEFORE it ships. Covers A0-A5 maturity lev... | `skill_view(name='adversarial-verifier')` |
| `agent-contract` | 1.0.0 | Core execution contract: real work, honest results, verified outputs, minimal changes. | `skill_view(name='agent-contract')` |
| `agent-flow` | 1.0.0 | Workflow router skill — classifies the incoming request into one of 12 patterns and dispatches to the corre... | `skill_view(name='agent-flow')` |
| `alembic-enum-double-create` | 1.0.0 | Use when alembic fails DuplicateObject enum on fresh DB. | `skill_view(name='alembic-enum-double-create')` |
| `api-documentation` | 1.0.0 | API documentation standards and tooling: OpenAPI/Swagger specs, endpoint descriptions, request/response sch... | `skill_view(name='api-documentation')` |
| `architecture-review` | 1.2.0 | Multi-role architecture review (a.k.a. HC-Party) with weighted decision matrices, conflict resolution, and... | `skill_view(name='architecture-review')` |
| `background-job-queue` | 1.0.0 | Add durable background job processing to a FastAPI/asyncpg app using arq. Covers project layout, job functi... | `skill_view(name='background-job-queue')` |
| `batch-job-optimization` | 1.0.0 | Systematically analyze and optimize database-bound batch processing jobs (imports, exports, ETL, bulk updat... | `skill_view(name='batch-job-optimization')` |
| `change-checklist` | 2.0.0 | Mandatory pre-ship verification before calling end_change(). Covers Phase 0 survey, test, multi-OS, multi-r... | `skill_view(name='change-checklist')` |
| `change-test-loop` | 1.1.0 | Small changes with real verification, bounded retries, self-healing. | `skill_view(name='change-test-loop')` |
| `code-review` | 3.0.0 | Two-axis pre-commit review: Standards (documents + code smells) and Spec (requirement compliance) via paral... | `skill_view(name='code-review')` |
| `code-wiki` | 0.1.0 | Generate wiki docs + Mermaid diagrams for any codebase. | `skill_view(name='code-wiki')` |
| `codebase-design` | 1.0.0 | Deep module vocabulary and design principles — module, interface, depth, seam, adapter, leverage, locality.... | `skill_view(name='codebase-design')` |
| `dev-plan` | 2.1.0 | Plan mode: write an actionable markdown plan to .hermes/plans/, no execution. Bite-sized tasks, exact paths... | `skill_view(name='dev-plan')` |
| `documentation-auditing` | 1.0.0 | Audit documentation for stale file paths, broken cross-references, and correctness gaps. Systematic approac... | `skill_view(name='documentation-auditing')` |
| `engineering-approach` | 1.9.0 | Engineering and communication standards for this project: terse, direct, skip explanations, always handle e... | `skill_view(name='engineering-approach')` |
| `error-handling` | 1.0.0 | Error handling patterns and idioms: structured exceptions, graceful degradation, retry strategies, circuit... | `skill_view(name='error-handling')` |
| `legacy-codebase-navigation` | 1.0.0 | Navigate, understand, and debug large legacy codebases (Rails, Django, early Node). Techniques for tracing... | `skill_view(name='legacy-codebase-navigation')` |
| `lesson-aware-agent` | 1.0.0 | Universal lesson-aware injection pattern. Makes every agent action memory-aware: search lessons before acti... | `skill_view(name='lesson-aware-agent')` |
| `logging-patterns` | 1.0.0 | Structured logging conventions: log levels, format standards, context injection, correlation IDs, sensitive... | `skill_view(name='logging-patterns')` |
| `mcp-server-building` | 1.0.0 | Build, test, and debug MCP servers for Hermes Agent — logging, dependency checks, fix hints, and best pract... | `skill_view(name='mcp-server-building')` |
| `memory-architecture` | 1.0.0 | Design and maintain agent memory system: MEMORY.md structure, privacy boundaries, gitignore per brain sourc... | `skill_view(name='memory-architecture')` |
| `product-requirements` | 1.0.0 | Concise 1-page PRD template: problem, scope, functional/non-functional requirements, edge cases, acceptance... | `skill_view(name='product-requirements')` |
| `project-map` | 1.0.0 | Structural project analysis — build a dependency graph so agents | `skill_view(name='project-map')` |
| `prove-before-create` | 1.0.0 | Enforce the "prove existing can't handle it" discipline before creating any new file. Supplements survey-be... | `skill_view(name='prove-before-create')` |
| `public-contribution` | 1.0.0 | After any improvement, bug fix, workflow discovery, or lesson — pause and evaluate whether the insight is p... | `skill_view(name='public-contribution')` |
| `rails-data-pipeline-debugging` | 1.2.0 | Debugging data transformation bugs in legacy Rails apps — tracing heuristic text-splitting, internationalis... | `skill_view(name='rails-data-pipeline-debugging')` |
| `react-best-practices` | 1.0.0 | 70+ React & Next.js performance optimization rules from Vercel Engineering — covers waterfalls, bundle size... | `skill_view(name='react-best-practices')` |
| `react-component-testing` | 1.0.0 | React component testing patterns — mocking UI libraries (recharts), React Query, MSW with direct fetch, fil... | `skill_view(name='react-component-testing')` |
| `react-composition-patterns` | 1.0.0 | React composition patterns that scale — compound components, state lifting, context interfaces, and avoidin... | `skill_view(name='react-composition-patterns')` |
| `react-view-transitions` | 1.0.0 | Implement smooth native-browser animations between UI states using React's ViewTransition component and doc... | `skill_view(name='react-view-transitions')` |
| `reasoning-patterns` | 1.0.0 | Select and apply reasoning patterns for any task — Plan-Execute-Verify, ReAct, Reflexion, or Tree of Though... | `skill_view(name='reasoning-patterns')` |
| `reflexion-check` | 1.0.0 | Pre-delivery self-critique: five-question audit to catch blind spots, verify claims, and score confidence b... | `skill_view(name='reflexion-check')` |
| `repo-organization` | 1.1.0 | Canonical repo organization for Hermes Cortex — structure, naming, consolidation, symlinks, and audit proce... | `skill_view(name='repo-organization')` |
| `requirements-elicitation` | 1.2.0 | Requirements elicitation for Hermes Cortex (a.k.a. elicit) — structured domain exploration, RICE/MoSCoW pri... | `skill_view(name='requirements-elicitation')` |
| `rest-graphql-debug` | 1.2.0 | Debug REST/GraphQL APIs: status codes, auth, schemas, repro. | `skill_view(name='rest-graphql-debug')` |
| `root-cause-debugging` | 2.0.0 | 6-phase root cause debugging: feedback loop, reproduce, pattern, hypothesise + instrument, fix, cleanup. Un... | `skill_view(name='root-cause-debugging')` |
| `save-lesson` | 1.0.0 | Auto-save a bug-fix lesson after resolving any non-trivial error. | `skill_view(name='save-lesson')` |
| `session-manager` | 1.1.0 | Session management skill — checkpoint/restore, context compression, progress tracking, and recovery for mai... | `skill_view(name='session-manager')` |
| `session-orchestration` | 1.0.0 | Five-wave session orchestration: Discovery → Impl-Core → Impl-Polish → Quality → Finalization. Quality gate... | `skill_view(name='session-orchestration')` |
| `state-orchestrator` | 1.0.0 | Information routing decision matrix for Hermes Cortex agents. Defines when to consult live context vs sessi... | `skill_view(name='state-orchestrator')` |
| `story-decomposition` | 1.0.0 | Break features into user-visible, testable stories using vertical slicing patterns. | `skill_view(name='story-decomposition')` |
| `storybook-setup` | 1.0.0 | Set up Storybook with Next.js (Vite) + Tailwind CSS + @storybook/test — init, Tailwind wiring, story patter... | `skill_view(name='storybook-setup')` |
| `subagent-driven-development` | 1.2.0 | Execute plans via delegate_task subagents (2-stage review). | `skill_view(name='subagent-driven-development')` |
| `survey-before-action` | 1.4.0 | Mandatory pre-flight checklist before creating or modifying any file. Prevents redundant work by systematic... | `skill_view(name='survey-before-action')` |
| `task-decomposition` | 1.0.0 | Break large tasks into discrete, verifiable, independently completable units. Uses functional decomposition... | `skill_view(name='task-decomposition')` |
| `test-seed-uniqueness` | 1.0.0 | Ensure test seed data never causes unique constraint violations — UUID-based, timestamp-based, counter-base... | `skill_view(name='test-seed-uniqueness')` |

## Spiritual Disciplines (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `agent-daily-bible-reading` | 1.0.0 | Daily bible reading cron pattern — generates SOUL.md entries and brain pages for agent-wide scripture engag... | `skill_view(name='agent-daily-bible-reading')` |

## Video Content Strategist (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `video-content-strategist` | 1.0.0 | Use when planning video content strategy, writing video scripts, optimizing YouTube channels, building shor... | `skill_view(name='video-content-strategist')` |

## Web Development (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `page-agent` | 1.0.0 | Embed an in-page natural-language GUI copilot in web apps. | `skill_view(name='page-agent')` |

## Workflow (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `task-start` | 1.0.0 | MANDATORY first action for every task. Bundles the complete pre-task sequence into one reference. Load this... | `skill_view(name='task-start')` |

## X Twitter Growth (1 skill)

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `x-twitter-growth` | 1.0.0 | X/Twitter growth engine for building audience, crafting viral content, and analyzing engagement. Use when t... | `skill_view(name='x-twitter-growth')` |

## Infrastructure Scripts (deployed via cortex-update.sh)

| Script | Type | Purpose | Schedule |
|--------|------|---------|----------|
| `agent-learning-collector.py` | no_agent | Agent-side: collects skills delta, lessons delta, session stats; sends Learning Report to the orchestrator inbox via Agent Bus | every 6h per agent |

## Social Media

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `client-brand-brand-marketing` | 1.0.0 | Full brand marketing for The Client Brand (@client-brand.co) — sustainable fashion bags, faith-driven, voice strategy, social media, content calendars, copy templates, email sequences, product storytelling | `skill_view(name='client-brand-brand-marketing')` |

## Productivity

| Skill | Version | Purpose | Load With |
|-------|---------|---------|-----------|
| `korean-language-learning` | 1.0.0 | Warm Korean language companion for English speakers 50+ — Hangul, grammar, honorifics, pronunciation, Anki strategies, reading progression, cultural context, conversation scripts | `skill_view(name='korean-language-learning')` |

## Naming Convention

Skills ported from AgentKore were renamed from `ak-*` to `hc-*`:
- `ak-elicit` → `requirements-elicitation`
- `ak-party` → `architecture-review`

All cross-references in other skills have been updated. No stale `ak-`
references remain.

## Notes

- **`test-driven-development`** and **`writing-plans`** have been merged into
  `change-test-loop` (v2.0.0) and `plan` (v2.1.0) respectively — they are no
  longer standalone skills.
- **`skill-from-lesson`** has been absorbed into `save-lesson` (v1.1.0).
- **`documentation-maintenance-audit`** has been absorbed into `project-readiness`
  (local-only, not yet contributed to the public repo).
- All skills within a category share consistent tooling conventions.

## Version History

| Date | Change |
|------|--------|
| 2026-06-11 | Initial manifest — 9 skills ported from AgentKore |
| 2026-06-11 | TDD merged into change-test-loop (v1.1.0), writing-plans merged into plan (v2.1.0) |
| 2026-06-09 | Added public-contribution, skill-from-lesson (software-development), nginx-web-app-deployment (devops), SOUL.md template, updated nginx template |
| 2026-06-09 | Added pr-review (github), package-security (devops). skill-from-lesson absorbed into save-lesson (v1.1.0). documentation-maintenance-audit absorbed into project-readiness. |
| 2026-06-15 | Added inbox-remediation devops skill v1.0.0 — auto-remediate hermes-cortex issues from agent inbox messages |
| 2026-06-15 | orch-weekly-auto-fix v1.1.0 — added verification phase: each fix re-checks its condition post-fix with PASS/FAIL/WARN output |
| 2026-06-17 | Added skill collection pipeline: collect-agent-skills.sh (agent-side reporter), request-skill-reports.sh (Moses orchestrator), process-skill-reports.py (digest compiler). Inbox server filename collision fix (microsecond precision). |
|| 2026-06-12 | **Memory That Compounds** — change-test-loop v2.0.0 adds LEARN phase (search lessons before every code change). New lesson-aware-agent skill for universal injection. Daily lesson auto-miner (02:00 KST). Compound stats dashboard (02:30 KST). Replaced weekly mining with daily mining. |
|| 2026-07-07 | **Pocock Upgrade** — Three skills imported/upgraded from Matt Pocock's skills repo (159k ★). New `codebase-design` (deep module vocabulary). `root-cause-debugging` v2.0 (6-phase with feedback loop). `code-review` v3.0 (two-axis Standards + Spec with Fowler smells). Integrated into agent-flow and architecture-review. |
