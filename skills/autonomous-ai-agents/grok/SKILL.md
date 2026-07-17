--- Full content (truncated) ---
---
name: grok
description: "Delegate coding to xAI Grok Build CLI (features, PRs)."
version: 0.1.0
author: Matt Maximo (MattMaximo), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Grok, xAI, Code-Review, Refactoring, Automation]
    related_skills: [codex, claude-code, hermes-agent]
---

# Grok Build CLI — Hermes Orchestration Guide

Delegate coding tasks to [Grok Build](https://docs.x.ai/build/overview) (xAI's
autonomous coding agent CLI, the `grok` command) via the Hermes terminal. Grok
can read files, write code, run shell commands, spawn subagents, and manage git
workflows. It runs three ways: an interactive TUI, **headless** (`-p`), and as
an **ACP agent** over JSON-RPC.

This is the third sibling to `codex` and `claude-code`. The orchestration
pattern is nearly identical — **prefer headless `-p` for one-shots**, use a PTY
for interactive sessions.

## When to use

- Building features
- Refactoring
- PR reviews
- Batch is
... [truncated]
--- End skill ---