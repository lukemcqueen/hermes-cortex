# Agent Guidelines — Hermes Cortex

This file is read by many agent tools (Claude Code, Copilot, Codex, Hermes, etc.)
on session start. It orients any agent working on this repo.

> **🪪 Scope:** This file serves two audiences:
> - **General agents** — the Architecture Principles, Agent Execution Contract, and
>   Structured Development Pipeline below are universal to Hermes Cortex and
>   recommended for every agent.
> - **Luke's deployment (Moses server)** — sections marked with a `⚡` tag are specific
>   to Luke's multi-machine, multi-agent orchestration setup. If you are not running
>   Luke's setup, treat these as examples you can adapt.
>
> Everything unmarked is general Hermes Cortex guidance — apply it to any project
> using this repo.

---

## What This Repo Does

Hermes Cortex is a **public installer and skill set** for
[Hermes Agent](https://hermes-agent.nousresearch.com). A fresh install gets:

- **Ollama** — local LLM server for free embeddings
- **Bun + gbrain** — persistent knowledge brain (PGLite, zero-config)
- **Langfuse** — LLM trace evaluation and scoring
- **Cortex Dashboard** — companion dashboard for Langfuse + system health
- **Brain dirs** — MECE-organized knowledge sources per user
- **gbrain sync daemon** — automatic 2-minute sync (autopilot preferred; sync-watch
  fallback if absent)
- **Hermes plugin** — `/brain` slash command for knowledge queries
- **Utility scripts** — heartbeat, memory sync, system health, LLM scoring

---

## Quick Reference Map

| What | Where |
|------|-------|
| Full doc index | `docs/DOCS-INDEX.md` |
| Full skill catalog (41 skills) | `docs/SKILLS-MANIFEST.md` |
| Security guide | `docs/SECURITY.md` |
| System architecture | `docs/architecture.md` |
| Langfuse + ClickHouse deploy | `deploy/README-langfuse-clickhouse.md` |
| Troubleshooting | `docs/troubleshooting.md` |
| Installer (27 steps, idempotent) | `install.sh` |

---

## Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Troubleshooting, guides, templates, SECURITY.md |
| `docs/templates/` | Seed MEMORY.md, USER.md, brain .gitignore |
| `install.sh` | Single-command installer, 27 steps (idempotent) |
| `deploy/` | Langfuse + ClickHouse deployment (docker-compose, configs, README) |
| `src/scripts/` | Utility + orchestration scripts (heartbeat, health, cron install, etc.) |
| `src/skills/` | Canonical skill sources (recursively copied to `~/.hermes/skills/`) |
| `scripts/` | Machine-specific scripts (not tracked: post-install, per-host helpers) |
| `.hermes-cortex/sessions/` | Active session state + archived snapshots |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `.hermes-cortex/memory/` | Per-user agent memory (gitignored) |
| `agent-inbox-private/` | Dedicated inbox repo — all agent messages (git-backed) |

---

## Cortex Project Directory Convention

This repo uses `.hermes-cortex/` for agent infrastructure, keeping the root focused
on source code and public docs.

```
project-root/
├── .hermes-cortex/           # Agent infrastructure (hidden, near code)
│   ├── sessions/
│   │   ├── current.md        # Active session (cron updates this)
│   │   └── archive/          # Timestamped session snapshots
│   ├── memory/               # Gitignored — per-user MEMORY.md, USER.md
│   ├── skills/               # Tracked — project-specific Hermes skills
│   └── .gitkeep
├── AGENTS.md                 # Stays at root — tool convention
└── docs/                     # Stays at root — team docs
```

### Three-layer data model

| Layer | Location | Content | Update cadence |
|-------|----------|---------|---------------|
| Hot session | `.hermes-cortex/sessions/current.md` | Branch, recent commits, task context | Every 30-120 min (cron) |
| Agent memory | `.hermes-cortex/memory/` | Compact pointers, user profile | Every session |
| Durable knowledge | `~/brain/<project>/` | Decisions, recipes, lessons | Weekly / as-needed |

---

## Architecture Principles

- **Two-repo system:** This public repo (open-source, MIT) + a private repo for
  personal config, secrets, and `brain-*` branches
- **PII-scrubbed:** No personal paths, domains, or credentials in this repo
- **Pointer memory pattern:** `MEMORY.md` keeps compact pointers (~2,200 chars),
  full detail lives in brain directories via gbrain
- **Privacy by default:** Memory files (`MEMORY.md`, `USER.md`) are gitignored in
  every brain source — never cross-contaminate instances
- **Memory scoring rubric:** Entries must score ≥7/12 before writing
  (relevance 4, accuracy 4, conciseness 2, durability 2) — see `memory/README.md`
- **State routing:** Information flows through a decision matrix — live context →
  session history → memory → docs, in that priority order — see
  `src/skills/software-development/state-orchestrator/`
- **Project separation:** Each project gets its own gbrain source for isolation —
  see `docs/knowledge-isolation-architecture.md`
- **Structured development pipeline:** Work flows through a defined chain —
  `requirements-elicitation` → `architecture-review` → `product-requirements` →
  `story-decomposition` → `change-test-loop` → code review — each stage consumes
  the output of the prior one, reducing rework and enforcing quality gates before
  code is written
- **Agent execution contract:** Non-negotiable rules below.

---

## Agent Execution Contract

Every agent working in this repo must follow these non-negotiable rules:

1. **Real execution, no simulation** — run actual commands, write real files,
   verify with tests. Never fabricate a result.
2. **Verified deliverables** — every change must be exercised and confirmed working
   before reporting done.
3. **Fix root causes, not symptoms** — when finding a bug, check sibling call paths
   for the same flaw.
4. **Touch only what the task needs** — no drive-by refactors, renames, or
   reformatting.
5. **Batch independent lookups** — when several reads/searches don't depend on each
   other, issue them together.
6. **Report blockers honestly** — if a tool/install/network call fails, say so
   directly and try an alternative. Never fabricate output.
7. **State confidence explicitly** — when uncertain, say so and explain what you
   know vs what you assume.
8. **Keep working until done** — don't stop after a stub, plan, or single command.
9. **Use tools, not descriptions** — every response must contain tool calls that
   make progress or deliver a result.
10. **Score every change** — every code change, config change, script edit, or
    deployment must be logged to the loop-governance DB (see Loop Governance
    section below). No exceptions.
11. **Tests/TDD/scoring are always the default** — every code change assumes
    RED-GREEN-REFACTOR and loop-governance scoring. Only explicit opt-out phrases
    (`"skip tests"`, `"read-only"`, `"throwaway prototype"`) bypass the loop.
    Ambiguous phrases (`"sure"`, `"go ahead"`, `"do it"`) still trigger the full
    loop.
12. **Tag discovered issues as follow-ups, don't fix them inline** — when you find
    a pre-existing bug during other work: document it with `todo`, complete the
    current slice first, then return to follow-ups in priority order. Never
    silently skip a discovered issue.
13. **Pull before push, always** — before any `git push`, fetch and rebase:
    `git pull --rebase origin <branch>`. Set `SKIP_PRE_PUSH=1` to bypass on a
    specific push.

---

## Loop Governance — Quick Reference

Every change must be scored. Two paths:

**Path A — MCP tools (for agents with MCP access):**
```
Before coding: mcp_loop_governance_cache_search(query="task description")
After change:  mcp_loop_governance_cycle_query(task_id="<task>")
Feedback:      mcp_loop_governance_feedback_accept(cycle_id=N)
               mcp_loop_governance_feedback_override(cycle_id=N, ...)
```

**Path B — CLI tools (for scripts, pre-commit hooks, CI):**
```
score-cycle --task <id> --cycle <N> --code-file <file> --pass-pct <rate>
loop-feedback accept <id> / loop-feedback override <id> --note "..."
```

### Scoring guidelines

| Change Type | `--test-file` | `--pass-pct` |
|---|---|---|
| Code change (TDD cycle) | Test file | Actual test pass rate |
| Config/IT change | N/A (omit) | 100 if verified, 0 if failed |
| Script edit | Any invocation that proves it works | 100 if ran without error |
| Deployment | Health check or proof of life | 100 if healthy |

### Session init sequence

1. `mcp_loop_governance_config_show()` — check thresholds/weights
2. `mcp_loop_governance_cycle_stats(days=7)` — review recent scoring health
3. `mcp_loop_governance_cache_search(query="<current task>")` — learn from past
4. **`offline_code search "<current task>"`** — check offline corpus before web
   (If the task involves code patterns, config, or infrastructure)

### Multi-file scoring

| Pattern | What to do |
|---------|------------|
| One logical change across N files | Score once. Most representative file as `--code-file`. |
| Independent changes in same session | Score each with distinct task IDs. |
| Config changes across 2+ files | Score once. Omit `--test-file`. `pass-pct 100` if verified. |

### ⚡ LLM Judge Scorer (trace quality evaluation)

In addition to the rule-based `score-cycle`, a separate LLM-as-Judge scorer runs as a `no_agent` cron
and evaluates conversation trace quality in Langfuse using `qwen2.5-coder:1.5b`.

| Aspect | Detail |
|--------|--------|
| What | Scores every unscored Langfuse trace on helpfulness/clarity/depth/overall |
| When | Weekdays 12pm/8pm KST, weekends 10pm KST |
| Where | `~/.hermes/scripts/llm-judge-scorer.py` |
| Skill | `llm-judge-scorer` (load for setup/troubleshooting) |

**For agents:** If you see low `overall` scores on your traces, address the quality gaps
(conciseness, completeness, verification) before your next task. The scorer is a quality
feedback loop — it exists to help you improve.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `embedding failed` / Ollama refused | `ollama serve` or `brew services restart ollama` |
| `Model nomic-embed-text not found` | `ollama pull nomic-embed-text` (274 MB) |
| `DB locked` | Wait & retry, or `rm ~/.hermes/data/loop-governance.db-journal` |
| `score-cycle not found` | `bash ~/hermes-cortex/src/loop-governance/setup.sh --symlinks-only` |
| MCP tool returns error | `hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback:** If scoring is genuinely blocked (Ollama down, DB corrupt),
diagnose with `verify.sh`, fix when possible, never skip entirely.

### Enforcement layers

| Layer | What | Bypass |
|-------|------|--------|
| Pre-commit hook | Runs `score-cycle` on every commit | `SKIP_SCORE=1` |
| SOUL.md directive | Rule in every Hermes session prompt | Remove directive |
| Cron auditor | Scans every 6h for unscored changes | N/A |

### Setup

```bash
bash ~/hermes-cortex/src/loop-governance/setup.sh
hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance
ollama pull nomic-embed-text
bash ~/.hermes/scripts/install-score-hook.sh --all
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```

---

## Skill Miner (Automated, Weekly)

`skill-miner` runs every Monday 6am on each agent. It scans local data for
reusable patterns, scores with nomic-embed-text, sends top findings to Moses
via agent inbox. No manual effort needed.

**What it mines:** Loop governance DB (high-scoring cycles), session history
(successful patterns), agent memory, custom skills not yet in the repo.

**Output:** Top 5 findings sent to `to=moses` with `cc=luke` via agent inbox.

---

## Autonomous Agent Reliability Patterns

Based on Karpathy's research (41% → 3% mistake rate reduction with explicit
constraints):

- **Task Contract** — For 3+ step tasks, define goal/success criteria/constraints
  before executing. Template: `docs/templates/task-contract.md`
- **Checkpoint Verification** — Verify each step before proceeding.
- **Conflict Surfacing** — Surface conflicting patterns explicitly. Do not blend
  silently.
- **Read-Before-Write** — Read a file before editing it unless creating from
  scratch.
- **Eval-Driven Development** — Define evals BEFORE building. Skill: `eval-harness`.

---

## Structured Development Pipeline

When building features or making significant changes, use this workflow:

```
requirements-elicitation → architecture-review → product-requirements →
story-decomposition → change-test-loop → code-review
```

Load the relevant skill with `skill_view(name)` when entering each stage.

| Stage | Skill | Output |
|-------|-------|--------|
| Elicit | `requirements-elicitation` | Structured requirements from user goals |
| Review | `architecture-review` | Architecture review w/ weighted decision matrix |
| Spec | `product-requirements` | 1-page PRD — problem, solution, constraints |
| Slice | `story-decomposition` | Break feature into independently deliverable stories |
| Build | `change-test-loop` | LEARN-RED-GREEN-REFACTOR with lesson-aware memory |
| Review | `code-review` | Pre-commit review: security, quality, auto-fix |

---

## ⚡ Luke's Deployment: Daily Priority Check-in

| Time | Agent | Action |
|------|-------|--------|
| 8:00am KST | Titus | Analyzes repos, posts briefing as comment on GitHub issue #11 |
| 8:30am KST | Moses | Reads latest comment via `gh api`. Asks user for #1 priority. |

**Crons:** `titus-daily-briefing` (8:00am KST), `daily-priority-checkin` (8:30am KST).

---

## ⚡ Luke's Deployment: Cron Jobs Reference

| Cron | Schedule | Type | Purpose |
|------|----------|------|---------|
| `agent-auto-remediate` | `*/30 * * * *` | LLM+skill | Auto-fix cron/inbox/service issues |
| `remediation-sensor` | `*/5 * * * *` | no_agent | Companion diagnostics sensor |
| `service-recovery` | `*/5 * * * *` | no_agent | Auto-restart crashed services |
| `hermes-update` | `23 22 * * *` | no_agent | Daily Hermes upgrade + config migrate |
| `hermes-cortex-sync` | `33 22 * * *` | no_agent | Daily repo pull + tool re-sync |
| `system-alert-watchdog` | `*/30 * * * *` | no_agent | Resource threshold alerts |
| `inbox-sensor` | `*/10 * * * *` | no_agent | Detect new broadcast messages |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | Memory persistence to gbrain |
| `score-auditor` | `0 */6 * * *` | no_agent | Scans for unscored changes |
| `gbrain-nightly-dream` | `0 3 * * 6` | no_agent | Weekly gbrain knowledge enrichment |
| `gbrain-update-sync` | `0 2 * * 0` | no_agent | Weekly gbrain update + health check |
| `harvest-lessons` | `0 5 * * 1` | no_agent | Weekly lesson harvesting |
| `memory-pruning` | `0 4 * * 1` | LLM+prompt | Weekly memory consolidation |
| `auto-save-sessions` | `every 360m` | no_agent | Session state auto-save |
| `agent-daily-bible-reading` | `0 1 * * *` | LLM+skill | Daily Bible reading |
| `agent-daily-soul-refinement` | `0 23 * * *` | LLM+skill | Daily soul refinement |
| `llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | Weekday trace quality scoring |
| `llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | Weekend trace quality scoring |
| `offline-code-index` | `0 5 * * 0` | no_agent | Weekly corpus index refresh |
| **Orchestrator-only (Moses primary, Esther backup):** | | | |
| `orch-team-health` | `*/10 * * * *` | no_agent | Cross-agent health polling |
| `orch-team-messages` | `*/10 * * * *` | no_agent | Flag urgent agent messages |
| `process-agent-messages` | `*/10 * * * *` | LLM | Process inbox remediation markers |

**Management:**
```bash
hermes cron list
bash ~/.hermes/scripts/install-hermes-crons.sh          # install/update all
bash ~/.hermes/scripts/install-hermes-crons.sh --force  # recreate all
bash ~/.hermes/scripts/install-hermes-crons.sh --dry-run
bash ~/.hermes/scripts/install-hermes-crons.sh --uninstall
```

---

## Offline Code — Local Snippet Search & Generation

A **518-snippet corpus** across 32 categories, searchable and generatable entirely offline.
Agents: load the `offline-code` skill and search offline before reaching for `web_search`.

| Command | What it does |
|---------|-------------|
| `offline_code search "flask rest api"` | Semantic search (nomic-embed-text) → ranked snippets |
| `offline_code gen "binary search tree rust"` | RAG + qwen2.5-coder → generated code |
| `offline_code stats` | Corpus + index stats |

**Agent workflow:** Before `web_search` for code patterns, try `offline_code search` first. It's faster, free, and works offline. Load the `offline-code` skill for full usage docs.

**tirith MCP server:** When you need to check URLs or verify command safety, use the `tirith_*` MCP tools instead of raw `curl` — they're sandboxed and skip security prompts. Configure with:
```bash
hermes mcp add tirith --command tirith --args mcp-server
```

**Setup:** Symlink `src/offline/offline_code.sh` → `~/.hermes/bin/offline_code`. Index is auto-built on first `search`/`gen`. Deployed automatically by `cortex-update.sh`.

---

## Common Tasks

- **Add troubleshooting entry:** Edit `docs/troubleshooting.md`, update changelog
- **Add a template:** Place in `docs/templates/`, update `install.sh`
- **Modify install:** Edit `install.sh` — 27 steps, idempotent
- **Update Docker config:** Edit `deploy/docker-compose.langfuse.yml`
- **Upgrade gbrain:** See `docs/gbrain-v2-taxonomy.md`
- **Install scoring hooks:** `bash ~/.hermes-cortex/scripts/install-score-hook.sh --all`
- **Verify scoring:** `bash ~/.hermes-cortex/scripts/install-score-hook.sh --list`
- **Add SOUL.md directive:** Edit `~/.hermes/SOUL.md`

## Rules

- No secrets in this repo. `.env`, `*.pem`, `*.key` are gitignored.
- Keep docs current when changing install behavior.
- MIT License — be permissive.
