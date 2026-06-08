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
- **gbrain sync daemon** — automatic 2-minute sync
- **Hermes plugin** — `/brain` slash command for knowledge queries
- **Utility scripts** — heartbeat, memory sync, system health, LLM scoring

## Key Directories

| Path | Purpose |
|---|---|
| `docs/` | Troubleshooting, guides, templates, SECURITY.md |
| `docs/templates/` | Seed MEMORY.md, USER.md, brain .gitignore |
| `install.sh` | Single-command installer (idempotent) |
| `docker-compose.langfuse.yml` | Langfuse v3 with ClickHouse, MinIO, Redis |
| `.gitignore` | Excludes .agentkore, .env, memory files, secrets |

## Architecture Principles

- **Two-repo system:** This public repo (open-source, MIT) + a private repo for personal config, secrets, and `brain-*` branches
- **PII-scrubbed:** No personal paths, domains, or credentials in this repo
- **Pointer memory pattern:** `MEMORY.md` keeps compact pointers (~2,200 chars), full detail lives in brain directories via gbrain
- **Privacy by default:** Memory files (`MEMORY.md`, `USER.md`) are gitignored in every brain source — never cross-contaminate instances
- **Memory scoring rubric:** Entries must score ≥7/12 (relevance 4, accuracy 4, conciseness 2, durability 2) before writing — see `memory/README.md`
- **State routing:** Information flows through a decision matrix — live context → session history → memory → docs, in that priority order — see `skills/software-development/state-orchestrator/`
- **Project separation:** Each project gets its own Hermes profile, brain source, and gbrain isolation via `scripts/cortex-profile.sh` — see `docs/project-separation-architecture.md`
- **Agent execution contract:** Non-negotiable rules — real work, verified results, no simulation — see `skills/software-development/agent-contract/`

## Common Tasks

- **Add a troubleshooting entry:** Edit `docs/troubleshooting.md`, add new numbered section, update changelog
- **Add a template:** Place in `docs/templates/`, update `install.sh` step 9 to copy it during install
- **Modify install:** Edit `install.sh` — 14 steps, idempotent, safe to re-run
- **Update Docker config:** Edit `docker-compose.langfuse.yml` — Langfuse v3 requires specific env vars (see docs/troubleshooting.md)

## Rules

- No secrets in this repo — ever
- `.env`, `.env.*`, `*.pem`, `*.key` are gitignored
- `.agentkore/` is removed+gitignored — not part of this project
- Keep docs current when changing install behavior
- MIT License — be permissive with what's shared
