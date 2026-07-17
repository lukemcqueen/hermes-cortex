--- Full content (truncated) ---
---
name: ai-coding-agents
description: "Delegate coding tasks to external AI coding agent CLIs — Claude Code, Codex CLI, and OpenCode. Orchestration patterns, one-shot tasks, PR reviews, parallel work, and pitfalls for each agent."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding-agent, claude-code, codex, opencode, autonomous, orchestration, pty, delegation]
    related_skills: [hermes-agent, task-delegation, plan, github-code-review]
---

# AI Coding Agents — Hermes Orchestration Guide

Delegate coding tasks to external AI coding agent CLIs. This skill covers three agents:

- **Claude Code** (Anthropic) — `references/claude-code.md`
- **Codex CLI** (OpenAI) — `references/codex.md`
- **OpenCode** (provider-agnostic, open-source) — `references/opencode.md`

All three share the same orchestration pattern from Hermes: run one-shot tasks via `terminal()`, handle interactive sessions via PTY/tmux, monitor with `proce
... [truncated]
--- End skill ---