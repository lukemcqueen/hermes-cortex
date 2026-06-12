# Agent Guidelines — Hermes Cortex

This file is read by many agent tools (Claude Code, Copilot, Codex, etc.)
on session start. It orients any agent working on this repo.

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

## Key Directories

| Path | Purpose |
|------|---------|
| `docs/` | Troubleshooting, guides, templates, SECURITY.md |
| `docs/templates/` | Seed MEMORY.md, USER.md, brain .gitignore |
| `install.sh` | Single-command installer, 27 steps (idempotent) |
| `deploy/docker-compose.langfuse.yml` | Langfuse v3 with ClickHouse, MinIO, Redis |
| `.hermes-cortex/sessions/current.md` | Active session state — branch, commits, task context |
| `.hermes-cortex/sessions/archive/` | Timestamped session snapshots |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `.hermes-cortex/memory/` | Per-user agent memory (gitignored — each dev has their own) |
| `.gitignore` | Excludes .agentkore, .env*, *.pem, *.key, state.db, .hermes/, .hermes-cortex/memory/ |

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
- **Structured development pipeline:** Work flows through a defined chain — `hc-elicit` → `hc-party` → `prd-lite` → `story-slicing` → `change-test-loop` → code review — each stage consumes the output of the prior one, reducing rework and enforcing quality gates before code is written
- **Agent execution contract:** Non-negotiable rules — real work, verified results, no simulation — see `src/skills/software-development/agent-contract/`

## Common Tasks

- **Add a troubleshooting entry:** Edit `docs/troubleshooting.md`, add new numbered section, update changelog
- **Add a template:** Place in `docs/templates/`, update `install.sh` step 9 to copy it during install
- **Modify install:** Edit `install.sh` — 26 steps, idempotent, safe to re-run
- **Update Docker config:** Edit `deploy/docker-compose.langfuse.yml` — Langfuse v3 requires specific env vars (see docs/troubleshooting.md)

## Rules

- No secrets in this repo — ever
- `.env`, `.env.*`, `*.pem`, `*.key` are gitignored
- `.agentkore/` is removed+gitignored — not part of this project
- Keep docs current when changing install behavior
- MIT License — be permissive with what's shared

## Agent Handoffs

### 2026-06-12 — Titus: gbrain sync-watch vs autopilot conflict

**Problem:** `src/scripts/install-gbrain-sync.sh` creates a sync-watch daemon
(`com.gbrain.sync-watch`) that runs `gbrain sync --all --skip default` every
120s. But `gbrain autopilot` (a self-maintaining daemon that handles sync
internally every ~150s) holds an exclusive PGLite 0.4.x connection. Any
second process trying to open the same `brain.pglite` crashes with:
`PGLite failed to initialize its WASM runtime — Aborted()`.

This is NOT a WASM bug — it's a single-connection lock conflict with a
misleading error message.

**Fix (commit `7f2205d` — not yet pushed):**
- `install-gbrain-sync.sh` now checks for `com.gbrain.autopilot` first and
  skips sync-watch setup if autopilot is present
- `cortex-update.sh` restarts autopilot when present; sync-watch as fallback
- `cortex-health.sh`, `heartbeat.py`, `dashboard/server.py`, `install.sh`
  verify script all check autopilot first, fall back to sync-watch
- After this fix, running `install.sh` on a system with autopilot will
  output: `gbrain autopilot detected — autopilot handles sync internally,
  skipping sync-watch`

**For existing installs that already have both daemons:**
Stop the redundant one: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.gbrain.sync-watch.plist`
Disable it: `mv ~/Library/LaunchAgents/com.gbrain.sync-watch.plist{,.disabled}`
Or re-run `install.sh` and the new guard will skip re-creating it.
