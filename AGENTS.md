# Agent Guidelines — Hermes Cortex

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## What This Repo Does

Hermes Cortex is a **public installer and skill set** for
[Hermes Agent](https://hermes-agent.nousresearch.com). A fresh install gets:

- **Ollama** — local LLM server for free embeddings
- **Bun + gbrain** — persistent knowledge brain (PGLite, zero-config)
- **Langfuse** — LLM trace evaluation and scoring
- **Cortex Dashboard** — companion dashboard for Langfuse + system health
- **Brain dirs** — MECE-organized knowledge sources per user
- **gbrain sync daemon** — automatic 2-minute sync (autopilot preferred; sync-watch fallback if absent)
- **Hermes plugin** — `/brain` slash command for knowledge queries
- **Utility scripts** — heartbeat, memory sync, system health, LLM scoring

## Ollama Model Tier

Hermes Cortex ships a **two-model stack** plus a unified env-var configuration
system:

### Unified Model Configuration (`~/.hermes/models.env`)

All Ollama model names are configured in `~/.hermes/models.env`. This file
**survives `cortex-update.sh`** (it's outside the repo) — set your custom
models there once and they never get reverted.

| Env var | Purpose | Default |
|---------|---------|---------|
| `JUDGE_MODEL` | LLM-as-Judge scorer | `qwen2.5-coder:3b` |
| `EMBEDDING_MODEL` | Text embeddings (gbrain, session cache, loop scorer, offline_code) | `nomic-embed-text:v1.5` |
| `CODING_MODEL` | Code generation via offline_code | auto-detected by RAM |
| `CREATIVE_MODEL` | Reserved for future creative tasks | _(not yet wired)_ |

Resolution priority (every script follows this):
1. **Runtime env var** — `JUDGE_MODEL=mannix/qwen:7b python3 script.py`
2. **`~/.hermes/models.env`** — persistant per-agent config, never overwritten
3. **Script's hardcoded default** — last resort fallback shipped with the repo

To change a model across all tools, edit `~/.hermes/models.env`:

```bash
# Example: Titus uses a bigger judge model
echo 'JUDGE_MODEL=mannix/qwen2.5-coder:7b-iq3_xs' >> ~/.hermes/models.env
```

**Scripts that respect `models.env`:**

| Script | Env var read | Deployed to |
|--------|-------------|-------------|
| `llm-judge-scorer.py` | `JUDGE_MODEL` | `~/.hermes-cortex/scripts/` |
| `model-health-watchdog.py` | `JUDGE_MODEL` | `~/.hermes-cortex/scripts/` |
| `system-alert-watchdog.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/scripts/` |
| `loop_scorer.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/scripts/` |
| `session_cache.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/scripts/` |
| `loop-gov-mcp.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/tools/loop-governance/` |
| `offline_code.py` | `EMBEDDING_MODEL`, `CODING_MODEL` | `~/.hermes-cortex/offline/` |
| `lessons.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/offline/` |
| `session_mine.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/offline/` |
| `web_cache.py` | `EMBEDDING_MODEL` | `~/.hermes-cortex/web-cache/` |
| `cleanup-ollama.sh` | `EMBEDDING_MODEL` | `~/.hermes-cortex/scripts/` |
| `install-ollama.sh` | `EMBEDDING_MODEL` | `~/.hermes-cortex/scripts/` |

### Default Stack Values

| Tier | Model | Size | Role |
|------|-------|------|------|
| Embedding | `nomic-embed-text:v1.5` | 274 MB | Vector search (embeddings for search, RAG) |
| Unified gen/judge | `qwen2.5-coder:3b` | 1.9 GB | Code gen, classification, routing, quality gates |

> **⚠️ 64k context minimum required.** All local models used with Hermes Agent need at least 64k context for tool calls and conversation history. `qwen2.5-coder:3b` from the Ollama registry defaults to 32k — build it with 64k:
> ```bash
> ollama create qwen2.5-coder:3b -f <(echo -e "FROM qwen2.5-coder:3b\nPARAMETER num_ctx 65536")
> ```
> Larger variants (7b+) typically ship with 128k+ out of the box and pass the check automatically. The installer runs this check — see `install-ollama.sh build_qwen_model`. Set `CORTEX_REPO` env var if your repo is at a non-standard path.

This replaces the previous three-model stack with a unified **qwen2.5-coder:3b** model that handles both code generation and classification/judging. Agents should use it via `http://localhost:11434/api/generate` or `offline_code gen` for:

- ✅ Code generation (RAG-enhanced via offline_code)
- ✅ Alert/task classification
- ✅ Quality gate pass/fail checks
- ✅ Message routing decisions
- ✅ Fallback when cloud model is rate-limited

### Cron Architecture — Three-Tier Model

As of July 2026, agent crons follow a three-tier architecture based on task requirements:

| Tier | Approach | When to use | Examples | Cost |
|------|----------|-------------|----------|------|
| **no_agent + API** | Python script + single deepseek API call | Deterministic orchestration + one creative generation | `agent-daily-bible-reading`, `agent-remediate-apply` | $0 / ~$0.01/run |
| **LLM-driven (deepseek)** | Full agent loop on deepseek-v4-flash | Needs Hermes tools (session_search, memory, patch) | `agent-daily-soul-refinement`, `memory-pruning`, `agent-fixer`, `agent-inbox` | ~$0.01/run |
| **no_agent script** | Python/shell, no LLM | Deterministic checks, sensors, watchdogs | `remediation-sensor`, `model-health-watchdog`, `inbox-flag` | $0 |

**Migration from qwen2.5-coder:3b:** The 3B model is excellent for single-shot tasks (code gen, classification, pass/fail) but lacks the reasoning capacity for multi-step agentic workflows. Crons that need multi-tool chaining have been migrated to the first two tiers above.

**Key scripts:**
- `src/scripts/agent-daily-bible-reading.py` — no_agent script: reads SOUL.md, determines next canonical book, calls deepseek API for creative generation, appends to SOUL.md, reports result
- `src/scripts/agent-remediate-apply.py` — no_agent script: reads remediation-sensor output, applies deterministic fixes (nginx, services, disk, ollama), reports

To install these crons on a fresh Hermes install:
```bash
bash src/scripts/install-crons.sh
```

See `docs/model-tier-strategy.md` for full architecture, RAM budget, and integration points.

## Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Troubleshooting, guides, templates, SECURITY.md, **model-tier-strategy.md** |
| `docs/templates/` | Seed MEMORY.md, USER.md, brain .gitignore |
| `install.sh` | Single-command installer, 27 steps (idempotent) |
| `deploy/` | Langfuse + ClickHouse deployment (docker-compose, configs, README) |
| `deploy/docker-compose.langfuse.yml` | Langfuse v3.200.0 with ClickHouse, MinIO, Redis |
| `deploy/README-langfuse-clickhouse.md` | **📘 Start here** — Langfuse setup, ClickHouse crash fixes, Hermes wiring |
| `.hermes-cortex/sessions/current.md` | Active session state — branch, commits, task context |
| `.hermes-cortex/sessions/archive/` | Timestamped session snapshots |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `.hermes-cortex/memory/` | Per-user agent memory (gitignored — each dev has their own) |
| `agent-inbox-private/` | Dedicated inbox repo — all agent messages (git-backed) |
| `.gitignore` | Excludes .env*, *.pem, *.key, state.db, .hermes/, .hermes-cortex/memory/ |

## Cortex Project Directory Convention

This repo uses `.hermes-cortex/` for agent infrastructure, keeping the root
focused on source code and public docs. If you use Hermes Agent with this
repo, agents will check for `.hermes-cortex/` first and fall back to repo
root if absent.

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

Three-layer data model:

| Layer | Location | Content | Update cadence |
|-------|----------|---------|---------------|
| Hot session | `.hermes-cortex/sessions/current.md` | Branch, recent commits, task context | Every 30-120 min (cron) |
| Agent memory | `.hermes-cortex/memory/` | Compact pointers, user profile | Every session |
| Durable knowledge | `~/brain/<project>/` | Decisions, recipes, lessons | Weekly / as-needed |

## Architecture Principles

- **Two-repo system:** This public repo (open-source, MIT) + a private repo for personal config, secrets, and `brain-*` branches
- **PII-scrubbed:** No personal paths, domains, or credentials in this repo
- **Pointer memory pattern:** `MEMORY.md` keeps compact pointers (~2,200 chars), full detail lives in brain directories via gbrain
- **Privacy by default:** Memory files (`MEMORY.md`, `USER.md`) are gitignored in every brain source — never cross-contaminate instances
- **Memory scoring rubric:** Entries must score ≥7/12 (relevance 4, accuracy 4, conciseness 2, durability 2) before writing — see `memory/README.md`
| **State routing:** Information flows through a decision matrix — live context → session history → memory → docs, in that priority order — see `src/skills/software-development/state-orchestrator/`
- **Project separation:** Each project gets its own gbrain source for isolation — see `docs/knowledge-isolation-architecture.md`
- **Structured development pipeline:** Work flows through a defined chain — `requirements-elicitation` → `architecture-review` → `product-requirements` → `story-decomposition` → `change-test-loop` → code review — each stage consumes the output of the prior one, reducing rework and enforcing quality gates before code is written
- **Agent execution contract:** Non-negotiable rules — real work, verified results, no simulation.

---

## Agent Execution Contract

Every agent working in this repo must follow these non-negotiable rules:

1. **Real execution, no simulation** — run actual commands, write real files, verify with tests. Never fabricate a result.
2. **Verified deliverables** — every change must be exercised and confirmed working before reporting done. A stub, plan, or single command is not a deliverable.
3. **Fix root causes, not symptoms** — when finding a bug, check sibling call paths for the same flaw. Fix the class, not just the reported site.
4. **Touch only what the task needs** — no drive-by refactors, renames, or reformatting. Add only the imports and dependencies your code requires.
5. **Batch independent lookups** — when several reads or searches don't depend on each other, issue them together in one turn instead of one at a time.
6. **Report blockers honestly** — if a tool, install, or network call fails, say so directly and try an alternative. Never substitute fabricated output.
7. **State confidence explicitly** — when uncertain, say so and explain what you know vs what you assume. The user needs actual conviction level, not a confident-sounding guess.
8. **Keep working until done** — don't stop after writing a stub, plan, or single command. Work until you've actually exercised the code or produced the requested result.
9. **Use tools, not descriptions** — never describe what you would do without actually doing it. Every response must contain tool calls that make progress or deliver a final result.
10. **Score every change** — every code change, config change, script edit,
    or deployment must be logged to the loop-governance DB.

    > **⚡ Mandatory: pre-commit scoring hook** — every dev machine running
    > cortex-update has a global git pre-commit hook that auto-creates a
    > governance cycle on every commit. See `docs/pre-commit-scoring.md`.
    > Agents must never override or bypass this hook. `SKIP_SCORE=1` is for
    > emergencies only and must be explicitly approved.

    Two feedback paths (both result in a loop-governance DB entry):

    **Path A — MCP tools (for agents with MCP access; provides feedback):**
    - Before coding: `mcp_loop_governance_cache_search(query="task description")`
    - After change: `mcp_loop_governance_cycle_query(task_id="<task>")`
    - Provide feedback: `mcp_loop_governance_feedback_accept(cycle_id=N)`
      or `mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="...", note="...")`

    **Path B — Pre-commit hook (default, runs automatically):**
    The hook creates cycles with `score-cycle --task "precommit-<repo>-<branch>/<message-slug>" --cycle <N> --code-file <file> --pass-pct <rate>`.
    Agents should follow up with `loop-feedback accept/override` to close the
    feedback loop. For manual CLI use:
    `score-cycle --task <id> --cycle <N> --code-file <file> --prev-code-file <file> --pass-pct <rate>`
    `loop-feedback accept <id>` / `loop-feedback override <id> --note "..."`

    For changes with no tests, use `pass-pct 100` if verification succeeded,
    `pass-pct 0` if it failed. No exceptions — without this data the system
    cannot self-improve.

11. **Tests/TDD/scoring are always the default** — every code change assumes
    RED-GREEN-REFACTOR, loop-governance scoring, and the full discipline.
    This is not optional. Only explicit opt-out phrases bypass the loop:
    - `"don't test, do X"` / `"skip tests"` — explicitly waives TDD
    - `"only review..."` / `"read-only"` — investigation with no code change
    - `"throwaway prototype"` — explicitly marked as disposable
    - `"just check..."` / `"look at..."` — read-only, no code change
    Any ambiguous or permissive phrase (`"sure"`, `"go ahead"`, `"do it"`,
    `"sounds good"`) still triggers the full loop. Erring on the side of
    doing it is always correct. The user has explicitly stated they want
    the full governance loop on every interaction, every time.

12. **Tag discovered issues as follow-ups, don't fix them inline** — when
    you find a pre-existing bug, problem, or improvement opportunity during
    other work:
    - **Do NOT fix it right there.** Fixing derails the current slice and
      creates sprawl. The user has explicitly said this causes stress.
    - **Do document it immediately** as a specific, actionable follow-up
      task using the `todo` tool (add it to your active task list with
      status `pending`).
    - **Complete the current slice first.** Then return to the documented
      follow-ups in priority order.
    - **Never silently skip** a discovered issue. "I saw this problem but
      didn't do it" without documenting it means it's forgotten forever.
      Every discovered issue must be tracked, even if it won't be fixed
      this session.

13. **Pull before push, always** — before any `git push`, fetch and rebase:
    `git pull --rebase origin <branch>`. Pushing without pulling first
    can discard remote commits or create merge bubbles. If the remote
    has new commits, your push will be rejected anyway — pull first and
    save the round trip. Set `SKIP_PRE_PUSH=1` to bypass on a specific
    push.

---

## Loop Governance — Quick Reference

### Interface: MCP tools vs CLI

| Situation | Use | Example |
|-----------|-----|---------|
| Agent before coding | `cache_search(query)` | `mcp_loop_governance_cache_search(query="build user auth")` |
| Agent session init | `config_show()` + `cycle_stats()` | At session start, query current thresholds + recent stats |
| Agent after a cycle | `feedback_accept(id)` / `feedback_override(id, ...)` | Confirm or correct the decision |
| Agent reviewing cycles | `cycle_query(task_id="...")` | Check what was scored for a task |
| Pre-commit hook | `score-cycle --task ... --pass-pct ...` | Runs automatically on `git commit` |
| Script/CI pipeline | `score-cycle --task ... --json` | Programmatic scoring without MCP |

MCP tools require the loop-governance MCP server to be registered in
`config.yaml`. CLI tools require the symlinks created by `setup.sh`.

### Session initialization sequence

Every agent session working in this repo should start with:

1. `mcp_loop_governance_config_show()` — check current thresholds/weights
2. `mcp_loop_governance_cycle_stats(days=7)` — review recent scoring health
3. `mcp_loop_governance_cache_search(query="<current task description>")`
   — learn from past similar cycles before coding

The cache grows with each session and becomes more useful over time.
If the cache DB doesn't exist yet, the first query populates it — just
keep using it.

### Per-change scoring flow

Every change follows this pattern:

```
Before coding: cache_search(task_description) ← learn from past
[Coding work — RED-GREEN-REFACTOR or config change]
After verifying: cycle_query(task_id="story-name")  ← review the cycle
                 feedback_accept / feedback_override ← train the model
```

### Multi-file changes — how to score

When a single change touches multiple files:

| Pattern | What to do |
|---------|------------|
| One logical change across N files | Score once. Use the most representative file as `--code-file`. Describe scope in the task name. |
| Independent changes in same session | Score each logical change separately with distinct task IDs (e.g. `auth-endpoint`, `config-logging`) |
| Config changes across 2+ files | Score once. Omit `--test-file`. `pass-pct 100` if verified. |

For CLI scoring, `--code-file` should be the file that best represents
the change's purpose (typically the main implementation file, not config
or test files).

### Scoring guidelines by change type

| Change Type | `--test-file` | `--pass-pct` |
|---|---|---|
| Code change (TDD cycle) | Test file | Actual test pass rate |
| Config/IT change | N/A (omit) | 100 if verification passed, 0 if failed |
| Script edit | Any invocation that proves it works | 100 if ran without error |
| Deployment | Health check endpoint or proof of life | 100 if healthy |

The goal is not perfection — it's a record of what was changed, how it was
verified, and what the system decided. Every logged cycle trains the scoring
model. A config change scored at pass-pct 100 with no test file is far more
valuable than an unscored config change that silently breaks later.

### Troubleshooting scoring failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `embedding failed` / `Ollama connection refused` | Ollama not running | `ollama serve` or `brew services restart ollama` |
| `Model nomic-embed-text:v1.5 not found` | Model not pulled | `ollama pull nomic-embed-text:v1.5` (274 MB) |
| `DB locked` | Concurrent score-cycle process | Wait and retry, or `rm ~/.hermes/data/loop-governance.db-journal` |
| `score-cycle not found` | Symlink missing | `bash ~/hermes-cortex/src/loop-governance/setup.sh --symlinks-only` |
| `warning: all tests failed — score may be inaccurate` | Test suite broken | Fix tests first, then re-score |
| MCP tool returns `error` | MCP server not registered | `hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback protocol:** If scoring is genuinely blocked (Ollama down, DB
corrupt, network unreachable):
1. Diagnose with `bash ~/.hermes-cortex/tools/loop-governance/verify.sh`
2. If fix takes > 2 minutes, record the change manually by running
   `score-cycle` once the issue is resolved
3. Never skip entirely — the cron auditor will flag unscored changes

### Enforcement layers

| Layer | What | How to install | Bypass |
|-------|------|---------------|--------|
| Pre-commit hook | Runs `score-cycle` on every `git commit` | `bash ~/.hermes/scripts/install-score-hook.sh --all` | `SKIP_SCORE=1` |
| SOUL.md directive | Rule appears in every Hermes session's system prompt | Edit `~/.hermes/SOUL.md` (see README) | Remove the directive |
| Cron auditor | Scans every 6h for unscored changes | Auto-created by `install-crons.sh` | N/A |

### Setup first time

```bash
# Full install — deps, symlinks, config, crons
bash ~/hermes-cortex/src/loop-governance/setup.sh

# Register the MCP server (so agents can use MCP tools)
hermes mcp add \
  --command python3 \
  --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py \
  loop-governance

# Pull the embedding model (required for scoring)
ollama pull nomic-embed-text:v1.5

# Deploy pre-commit hooks across all repos
bash ~/.hermes/scripts/install-score-hook.sh --all

# Verify everything
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```

**Dependencies:** Ollama + **nomic-embed-text:v1.5** (for scoring — the only
model required). 274 MB. Run `bash src/loop-governance/cleanup-ollama.sh`
to remove unnecessary models and free disk space.

---

## ⚠️ Mandatory Agent Workflow: Loop Governance

**This is not optional.** Every agent working in this repo must follow this sequence for every change. It is not enough to read Rule #10 above — you must execute these calls.

### Before any work — cache_search

```python
# REQUIRED step before touching any file, config, or cron
mcp_loop_governance_cache_search(query="<what you are about to do>")
```

- Even if it returns nothing — the cache grows with use
- If it returns a similar past cycle, read it. It may save you repeating a mistake.
- If you skip this, you are flying blind.

### After EACH logical change — cycle_query + feedback

```python
# AFTER completing and verifying the change
mcp_loop_governance_cycle_query(task_id="<descriptive-name>")
# Then IMMEDIATELY:
mcp_loop_governance_feedback_accept(cycle_id=N, note="verified: <how you verified>")
# OR if the decision was wrong:
mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="MOVE_ON", note="...")
```

### What counts as one logical change

| Situation | Treat as |
|-----------|----------|
| N files changed for one purpose | One score |
| N independent changes in same session | N individual scores |
| Config + code that depend on each other | One combined score |
| Batch-scoring the entire session | ❌ Never acceptable |

### Enforcement

- **Pre-commit hook** runs `score-cycle` on every `git commit` in hermes-cortex
- **`scoring-activity-watchdog`** cron (14:00, 20:00 KST) alerts if too few cycles logged per day
- **Moses (orchestrator)** is scored on this same contract — no exceptions for the leader
- **Three un-scored changes** → agent must propose a technical enforcement mechanism

---

## Skill Miner (Automated, Runs Weekly)

`skill-miner` runs every Monday 6am on each agent's machine. It scans local data for reusable patterns, scores them with nomic-embed-text:v1.5, and sends top findings to Moses via the agent inbox automatically. No manual effort needed.

**What it mines (locally, PII-scrubbed):**
- Loop governance DB — high-scoring TDD cycles
- Session history — successful patterns from conversations
- Agent memory — MEMORY.md, USER.md content
- Custom skills — skills installed locally but not in the repo (full SKILL.md sent)

**Output:** Top 5 findings sent to `to=moses` (default) with `cc=luke` via the agent inbox. Moses reviews, consolidates, and pushes to hermes-cortex.

**Addressing:** Messages default to `to=moses`. Use `to=all` for broadcasts, `cc=agent` for carbon copies. Every message auto-CCs Luke.

## Autonomous Agent Reliability Patterns

Based on Karpathy's research (41% → 3% mistake rate reduction with explicit constraints):

- **Task Contract** — For 3+ step tasks, define goal/success criteria/constraints/checkpoints *before* executing. Template: `docs/templates/task-contract.md`
- **Checkpoint Verification** — Verify each step before proceeding. Fixing state retroactively is 10x harder.
- **Conflict Surfacing** — When detecting multiple patterns, surface the conflict explicitly. Do NOT blend silently.
- **Read-Before-Write** — Read a file before editing it unless creating from scratch. 90% of mistakes come from missing context.
- **Eval-Driven Development** — Define evals BEFORE building. Capability evals (new features) + regression evals (maintain ≥95%). Skill: `eval-harness`. Scripts: `run-evals.py`, `analyze-failures.py`.

---

## Structured Development Pipeline

When building new features or making significant changes, use this structured
workflow. Each stage consumes the output of the prior one, reducing rework
and enforcing quality gates before code is written:

```text
requirements-elicitation (structured requirements gathering)
    ↓
architecture-review (multi-role architecture review)
    ↓
product-requirements (concise product spec)
    ↓
story-decomposition (user-visible, testable stories)
    ↓
change-test-loop (RED-GREEN-REFACTOR with lessons)
    ↓
code-review (security scan, quality gate)
```

---

## ⚡ Daily Priority Check-in (Luke's multi-agent setup)

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## ⚡ Luke's Deployment: Daily Priority Check-in

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## ⚡ Luke's Deployment: Cron Jobs Reference

> Content relocated to [`docs/fleet-reference.md`](docs/fleet-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

## ⚡ Health Monitoring Pipeline

The orchestrator polls all server agents every 10 minutes for a compact **health vector** — a 9-element ternary status vector with no auth overhead, no secrets, no JSON bloat.

### Service map (shared across all agents)

| Index | Service | Code | Description |
|-------|---------|------|-------------|
| 0 | resources | 1=ok, -1=stressed, 0=n/a | CPU load < 4× cores, memory > 5% free |
| 1 | services | 1=ok, -1=down, 0=n/a | At least one core daemon reachable |
| 2 | no_errored_crons | 1=ok, -1=error, 0=n/a | No cron jobs with recent failures |
| 3 | no_stale_crons | 1=ok, -1=stale, 0=n/a | No cron jobs gone stale (orchestrator) |
| 4 | nginx | 1=up, -1=down, 0=n/a | nginx process running |
| 5 | ollama | 1=up, -1=down, 0=n/a | Ollama process running |
| 6 | gbrain | 1=up, -1=down, 0=n/a | gbrain sync daemon running |
| 7 | disk_ok | 1=ok, -1=full, 0=n/a | Root partition < 90% used |
| 8 | gbrain_sources_ok | 1=ok, -1=missing, 0=n/a | ~/brain dirs exist and non-empty |

### Health endpoint (server agents)

Each server agent runs `health-vector.py --serve <port>` as a systemd user service. The endpoint returns a single JSON line:
```json
{"v":[1,1,1,1,1,1,1,1],"h":"hostname","t":1700000000}
```
No authentication. No TLS. Plain HTTP — the vector contains no secrets, just binary up/down/n/a flags.

### Agent endpoint URLs

> **Private config:** Actual domains are set locally (not committed to the public repo).
> See `src/agent-registry.json` — each agent's `health_url` must be configured on the
> orchestrator for the poller to reach it. Port hints are in the description field.

| Agent | Port | Method | Auth |
|-------|------|--------|------|
| Moses | `127.0.0.1:13007` | HTTP poll (internal) | none |
| Gisu | `:13007` | HTTP poll | none |
| Kustos | `:13007` | HTTP poll | none |
| Joseph | `:12007` | HTTP poll | none |
| Esther | `:14007` | HTTP poll | none |
| Titus | pushes to Moses inbox | Inbox push | each agent's own credentials |

### How it works

1. **Server agents** (`health_method: "http"`): Moses' `orch-team-health.py` cron (`*/10 * * * *`) fetches each agent's vector via HTTP.
2. **Client-only agents** (`health_method: "inbox"`): Titus runs `health-vector-push.sh` via launchd every 10 minutes, POSTing his vector to Moses' inbox API with his own Basic Auth credentials.
3. **Change detection**: The poller fingerprints each vector. No output = no change. Alerts fire only on state transitions:
   - `🔴 Titus ❌ ollama` (service went down)
   - `✅ Titus — all services restored` (back to healthy)

### Deployment (each server agent)

> Content relocated to [`docs/setup-reference.md`](docs/setup-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

### Deployment (Titus / macOS client-only)

> Content relocated to [`docs/setup-reference.md`](docs/setup-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

### Files

| Path | Purpose |
|------|---------|
| `src/scripts/health-vector.py` | Health vector generator + HTTP server (cross-platform) |
| `src/scripts/health-vector-push.sh` | Inbox push script for client-only agents |
|| `src/scripts/orch-team-health.py` | Orchestrator poller (no_agent cron) |
|| `src/scripts/orch-health-report.py` | Health snapshot report — formatted for Telegram delivery |
|| `src/agent-registry.json` | Agent registry with `health_method`, `health_url` |
|| `docs/templates/com.hermes.health-push.plist` | macOS launchd template for Titus |
|| `docs/templates/health-vector.service` | systemd user service template for server agents |

### Health snapshot report

Moses sends a health snapshot to Luke on schedule via two no_agent crons:

| Cron | Schedule | What it does |
|------|----------|-------------|
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | Every hour Mon-Fri 9AM–6PM KST |
| `orch-health-report-saturday` | `0 11,17 * * 6` | Sat 11AM + 5PM KST |

The script (`orch-health-report.py`) reads the agent registry with local overrides, polls every agent's health endpoint, and outputs compact markdown with emoji status bars — designed for mobile Telegram. No LLM tokens used (no_agent script cron).

**To deploy on Esther (backup orchestrator):**

```bash
# 1. Copy the script
cp ~/hermes-cortex/src/scripts/orch-health-report.py ~/.hermes/scripts/orch-health-report.py

# 2. Create the crons
hermes cron create --name orch-health-report-weekday \
  --no-agent --script orch-health-report.py \
  --schedule "0 9-18 * * 1-5"

hermes cron create --name orch-health-report-saturday \
  --no-agent --script orch-health-report.py \
  --schedule "0 11,17 * * 6"

# 3. Set up her own agent-registry.local.json (see Moses' version for reference)
```

---

## ⚡ Agent Inbox Architecture

The agent inbox has two layers that are easy to confuse. Here's the truth:

### Two layers, not one

| Layer | What it does | Who runs it |
|-------|-------------|-------------|
| **API backend** (gateway :8903 + nginx) | Stores messages, serves the HTTP API | **Only Moses and Esther** (the gateway does this automatically) |
| **MCP client** (`inbox-mcp.py` in Hermes config) | Provides `inbox_send`/`inbox_read`/`inbox_watch` tools to the agent | **Every agent** — including Moses and Esther |

The confusion is that "agent inbox" sounds like one thing. It's two:
1. The **server** that holds the messages → only Moses & Esther
2. The **client tool** that lets an agent send/read messages → every agent needs this

### Architecture diagram

```
MOSES / ESTHER (inbox servers)          EVERY AGENT (including Moses & Esther)
─────────────────────────────           ─────────────────────────────────────
Hermes gateway (:8903)                  ~/.hermes/config.yaml
  ↳ built-in inbox API                    ↳ mcp_servers.agent-inbox
  ↳ stores messages                       ↳ runs inbox-mcp.py as subprocess
                                          ↳ reads ~/.hermes/moses-inbox.conf
nginx proxy (:13004 / :14004)              ↳ calls remote inbox API via HTTP
  ↳ SSL + Basic Auth                      ↳ exposes inbox_send/read/watch tools
  ↳ proxies → :8903
```

### What each agent needs

| Agent | Role | Runs API backend? | Runs MCP client? | Has `moses-inbox.conf`? |
|-------|------|-------------------|-------------------|------------------------|
| **Moses** | Primary orchestrator | ✅ YES — gateway :8903 + nginx :13004 | ✅ YES — inbox tools | ✅ Points to self |
| **Esther** | Backup orchestrator | ✅ YES — gateway :8903 + nginx :14004 | ✅ YES — inbox tools | ✅ Points to her own instance |
| **Gisu** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Joseph** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Kustos** | Remote server | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |
| **Titus** | macOS laptop | ❌ No — client only | ✅ YES — needs inbox-mcp.py in config | ✅ Points to Moses |

### Critical: You need a poll cron to receive messages

> Content relocated to [`docs/operations-reference.md`](docs/operations-reference.md) for focused reference.
> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._

### What "install the inbox" means

```
If you are Moses or Esther:
  └─ You already have the API backend (it's part of the Hermes gateway)
  └─ You already have the MCP client (it's in your config.yaml)
  └─ You just need the nginx proxy setup

If you are Gisu, Joseph, Kustos, or Titus (client agents):
  └─ You need the MCP client in your Hermes config.yaml:
       mcp_servers:
         agent-inbox:
           command: python3
           args: [~/hermes-cortex/src/mcp-servers/inbox-mcp.py]
           enabled: true
  └─ You need ~/.hermes/moses-inbox.conf with YOUR credentials
  └─ You DO NOT need to run an inbox server or nginx proxy
```

This configuration is set up automatically by `install.sh` / `install-crons.sh`. If you ran the installer, your `config.yaml` already has the `agent-inbox` MCP server entry. If not, add it manually.

### Setup checklist

**Every agent (Moses, Esther, Gisu, Joseph, Kustos, Titus):**
```bash
# 1. Pull repo
cd ~/hermes-cortex && git pull

# 2. Ensure MCP client is in config.yaml
grep -A4 "agent-inbox" ~/.hermes/config.yaml
# Should show: command: python3, args: [inbox-mcp.py], enabled: true

# 3. Create credentials file — YOUR OWN credentials
nano ~/.hermes/moses-inbox.conf
```
```ini
MOSES_INBOX_URL="https://your-domain.com:13004"
MOSES_INBOX_AUTH="your_username:your_password"
AGENT_NAME="your_agent_name"
```
```bash
chmod 600 ~/.hermes/moses-inbox.conf

# 4. Verify you can talk to the inbox
curl -s -u "your_username:your_password" \
  https://your-domain.com:13004/api/inbox?limit=3

# 5. Create inbox-check cron (every 30 min):
# hermes cron create ...
```

**Moses and Esther only — additionally:**
```bash
# Ensure nginx proxy exists (Moses: :13004 → :8903, Esther: :14004 → :8903)
# Already set up by install.sh — verify:
curl -s -u "your_username:your_password" https://your-domain.com:13004/api/inbox?limit=1
# Should return 200
```

### Common confusion to avoid

Key rule: only Moses and Esther run the inbox API backend. Every other agent just needs the MCP client (`inbox-mcp.py` in config.yaml) + credentials in `~/.hermes/moses-inbox.conf`. Do NOT share credentials — every agent has their own htpasswd user.

---

## Offline Code — Local Snippet Search & Generation

518-snippet corpus across 32 categories. **Mandatory agent workflow:**
1. `offline_code search "<pattern>"` — check corpus first
2. **Found?** Use it. Zero API cost.
3. **Not found?** `web_search()` as last resort
4. **If web succeeded:** `offline_code learn "<title>" ...` to fill the gap

Commands: `offline_code search`, `offline_code gen`, `offline_code learn`, `offline_code stats`.

**tirith MCP server:** Use `tirith_*` tools instead of raw `curl` for sandboxed URL/command checks. Configure: `hermes mcp add tirith --command tirith --args mcp-server`

Load `skill_view(name="offline-code")` for full usage docs.

---

## Common Tasks

- **Troubleshooting:** Edit `docs/troubleshooting.md`
- **Templates:** Place in `docs/templates/`, update `install.sh`
- **Install changes:** Edit `install.sh` (26 steps, idempotent)
- **Docker config:** Edit `deploy/docker-compose.langfuse.yml`
- **Scoring hooks:** `bash ~/.hermes-cortex/src/scripts/install-score-hook.sh --all` (or `--list`)

## Rules

- **No PII in this repo.** No personal paths, hostnames, emails, API keys, or tokens. Use placeholders (`$HOME/`, `~/`, `<username>`). Every agent MUST grep for personal identifiers before committing.
- No secrets. `.env`, `*.pem`, `*.key` are gitignored.
- Keep docs current when changing install behavior.

## ⚡ Fleet Reference (Luke's deployment)

### Agent summary

| Agent | Role | Host | Services | Inbox method |
|-------|------|------|----------|-------------|
| Moses | Primary orchestrator | moses-server (Linux) | Gateway + nginx proxy :13004 | HTTP poll (self) |
| Esther | Backup orchestrator | worker-5 (Linux) | Gateway + nginx proxy :14004 | HTTP poll (+bkup inbox) |
| Gisu | Remote server | worker-3 (Linux) | Health endpoint :13007 | HTTP poll → Moses inbox |
| Joseph | Remote server | worker-2 (Linux) | Health endpoint :12007 | HTTP poll → Moses inbox |
| Kustos | Remote server | worker-4 (Linux) | Health endpoint :13007 | HTTP poll → Moses inbox |
| Titus | macOS developer | LAM2 (Apple M1, 16GB) | Client only; Ollama crons use qwen2.5-coder:7b-iq3_xs | Push health to Moses inbox |

### Auto-remediation components

All in `src/scripts/`, installed by `install.sh` + `install-crons.sh`:

| Script | Type | Schedule | Purpose |
|--------|------|----------|---------|
| `cron-auto-remediate.sh` | Shell | On-demand | Diagnostics + fix actions (fix-missing, fix-git, fix-perms, fix-purge) |
| `system-alert-watchdog.py` | no_agent | Every 10m | Resource alerts + auto-cleanup |
| `service-recovery.py` | no_agent | Every 5m | Auto-restart nginx, Ollama, gbrain, Langfuse |
| `orch-team-messages.sh` | no_agent | Every 10m | Flags agent error messages with remediation markers |
| `agent-auto-remediate` (skill) | LLM cron | Every 5m | Checks errored crons + inbox remediation, applies fixes |

**Skill:** `src/skills/devops/auto-remediation/SKILL.md`
**Setup:** Silent when healthy, brief when fixes applied, escalate after 3 failures.

### Esther setup (backup orchestrator)

```bash
# 1. Copy agent registry
cp ~/.hermes-cortex/src/agent-registry.json ~/.hermes/state/agent-registry.json
# 2. Install crons
bash ~/.hermes-cortex/src/scripts/install-crons.sh
# 3. Copy orchestrator-specific scripts
cp ~/hermes-cortex/src/scripts/orch-moses-inbox-remediate.sh ~/.hermes/scripts/
cp ~/hermes-cortex/src/scripts/orch-weekly-auto-fix.py ~/.hermes/scripts/
# 4. Create orch-process-agent-messages cron (see agent-registry.json)
# 5. Start gbrain autopilot
gbrain autopilot --repo ~/brain/default --interval 300 &
# 6. Fix score-cycle symlink (verify.sh expects this)
ln -sf ~/.hermes-cortex/tools/loop-governance/score_cycle.py ~/.local/bin/score-cycle
```

**Known false positives:**
- `system-heartbeat` exits 1 with `❌ gbrain sync daemon: DOWN` on Linux (macOS-only service)
- Loop governance `verify.sh` reports 1 warning about CLI symlink until step 6 above is done

### All timestamps in KST (UTC+9)

All monitoring scripts output timestamps in Seoul time. Affects: `orch-team-health.py`, `system-alert-watchdog.py`, `service-recovery.py`, `orch-team-messages.sh`, and all cron outputs.

---

## ⚡ Inbox Message Decision Framework (All Agents)

Every agent processing inbox messages follows this framework.

### Three assessment axes

**Priority** (from message frontmatter):
| Priority | Means | Response |
|----------|-------|----------|
| `critical` | Service down, security issue, data loss | Immediate action, notify user |
| `urgent` | Needs same-day attention | Handle within current cron tick |
| `normal` | Standard task or FYI | Handle same cycle or escalate |
| `notification` | Informational only | Acknowledge and close |

**Actionability:**
| I have the tools | → AUTO-ACT — run fix, verify, report |
| Needs another agent | → DELEGATE — send inbox message, CC user |
| Needs human judgment | → ESCALATE — report to user with context + options |
| Notification only | → ACKNOWLEDGE — close, no action needed |

**Scope** (how much work):
| Simple (< 3 calls, < 2 min) | Do in cron session |
| Moderate (3-10 calls, investigate) | Do now, report result |
| Complex (> 10 calls, multi-step) | Escalate or offer guidance |
| Multi-agent | Send inbox message, CC user |

### Decision matrix

| Priority | Simple | Moderate | Complex | Multi-agent |
|----------|--------|----------|---------|-------------|
| **critical** | AUTO-ACT | AUTO-ACT | AUTO-ACT + notify | Delegate + notify |
| **urgent** | AUTO-ACT | AUTO-ACT | AUTO-ACT + report | Delegate + report |
| **normal** | AUTO-ACT | AUTO-ACT | Escalate | Escalate |
| **notification** | Acknowledge | Acknowledge | Acknowledge | Forward if needed |

### After-action requirements

Every action must deliver: **what** (single-line summary), **how verified** (tool output/confirmation), **evidence** (output excerpt), **cycle ID** (for code/config changes).

---

## ⚡ Doc Freshness: AGENTS.md + SOUL.md (All Agents)

### Enforcement layers

| Layer | What | Who runs | Frequency |
|-------|------|----------|-----------|
| **Weekly audit** | `agents-doc-audit.py` checks all SOUL.md + AGENTS.md for mandatory sections | Moses (orchestrator) | Every Monday 7am KST |
| **Post-update broadcast** | Moses sends inbox message to all agents after modifying AGENTS.md or his SOUL.md | Moses (orchestrator) | On change |
| **Daily soul refinement** | `agent-daily-soul-refinement` cron (Channel C) fills mandatory section gaps | Each agent's own cron | Daily 23:00 |
4. **Session-start check** — Every agent reads AGENTS.md + own SOUL.md at session start | Each agent | Every session |

### Mandatory sections

**SOUL.md:** Identity, Core Mission, Behavioral Principles (must include Loop Governance + Inbox Decision Framework), Communication Style, Scripture Insights

**AGENTS.md:** Agent Execution Contract, Loop Governance, Inbox Message Decision Framework, Doc Freshness: AGENTS.md + SOUL.md

### Audit script

```bash
python3 ~/hermes-cortex/src/scripts/agents-doc-audit.py
python3 ~/hermes-cortex/src/scripts/agents-doc-audit.py --json
```

### Update flow

1. Moses modifies AGENTS.md or his SOUL.md
2. Moses runs `agents-doc-broadcast.py` (or sends inbox message manually)
3. All agents get inbox message with summary
4. Each agent reads update on next cron tick

---

## ⚡ Agent Cron Management (all agents)

### Problem

Only Moses has the `cronjob` MCP tool. Other agents cannot manage their own
cron jobs directly. To request a cron change, any agent sends a structured
inbox message to Moses.

### Protocol

Load `skill_view(name="cron-management")` for the full protocol spec.

**Subject format:** `🔧 CRON: create|update|remove`

**Key fields:**
- `CRON_NAME` — required, lowercase with hyphens
- `CRON_SCHEDULE` — cron expression or interval (e.g. `0 9 * * *`, `*/30 * * * *`)
- `CRON_PROMPT` — self-contained prompt for LLM crons
- `CRON_SCRIPT` — script path for no_agent crons
- `CRON_MODEL` / `CRON_PROVIDER` — model pinning
- `CRON_DELIVER` — where output goes (origin, local, telegram:ID)
- `CRON_REASON` — why the change is needed

### Workflow

1. Agent sends inbox message to Moses with `🔧 CRON:` subject
2. Moses picks it up in his next `process-mcp-agent-inbox-messages` tick
3. Moses validates, applies the change, replies to sender, CC's Luke
4. Changes are scored to loop governance and traceable to the request

### Scope

- **Local crons** (on Moses' server) — Moses applies directly
- **Remote agent crons** (Titus/Gisu/Joseph's machines) — Moses creates a
  cron request inbox message for those agents to apply on their own, CC's Luke
  
### Universal Agent Crons

The following crons are registered by `install-crons.sh` on every agent.
Run `bash ~/hermes-cortex/src/scripts/install-crons.sh --dry-run` to
see what's missing on any agent, or `bash install-crons.sh --force` to
recreate all to match the repo definition.

| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `agent-auto-remediate` | LLM | `*/30 * * * *` | skill `auto-remediation` | origin |
| `remediation-sensor` | no_agent | `*/5 * * * *` | `remediation-sensor.py` | local |
| `system-alert-watchdog` | no_agent | `*/30 * * * *` | `system-alert-watchdog.py` | origin |
| `agent-cron-failure-scanner` | no_agent | `*/30 * * * *` | `agent-cron-failure-scanner.py` | local |
| `service-recovery` | no_agent | `*/5 * * * *` | `service-recovery.py` | origin |
| `inbox-sensor` | no_agent | `*/10 * * * *` | `inbox-sensor.py` | local |
| `score-auditor` | no_agent | `0 */6 * * *` | `score-auditor.py` | origin |
| `memory-to-brain-sync` | no_agent | `0 */6 * * *` | `memory-to-brain-sync.py` | local |
| `llm-judge-scorer-weekday` | no_agent | `0 12,20 * * 1-5` | `llm-judge-scorer.py` | local |
| `llm-judge-scorer-weekend` | no_agent | `0 22 * * 0,6` | `llm-judge-scorer.py` | local |
| `offline-code-index` | no_agent | `0 5 * * 0` | `offline_code_index_cron.sh` | local |
| `model-health-watchdog` | no_agent | `0 7 * * *` | `model-health-watchdog.py` | origin |
| `process-mcp-agent-inbox-messages` | LLM | `0 6-23 * * *` | prompt: inbox poll + cron failure check | origin |

LLM crons should be pinned to the provider/model specified in the repo's
`deploy/config/config.yaml` or the agent's profile. The installer sets
model/provider for known LLM crons via `pin_cron_model()`.
  
