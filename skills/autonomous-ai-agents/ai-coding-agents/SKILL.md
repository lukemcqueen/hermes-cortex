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

- **Claude Code** (Anthropic) — `claude` CLI
- **Codex CLI** (OpenAI) — `codex` CLI
- **OpenCode** (provider-agnostic, open-source) — `opencode` CLI

All three share the same orchestration pattern from Hermes: run one-shot tasks via `terminal()`, handle interactive sessions via PTY/tmux, monitor with `process(action='poll')`, and review the diff before integrating.

## Common Orchestration Pattern

### 1. One-shot tasks (headless, preferred)

```bash
# Claude Code
claude -p "Add rate limiting to the login endpoint" --output-format text

# Codex (headless)
codex exec "Add rate limiting to the login endpoint"

# OpenCode
opencode run "Add rate limiting to the login endpoint"
```

One-shots are deterministic, testable, and fit in a terminal call. **Prefer
headless for anything with a clear definition of done.**

### 2. Interactive sessions (PTY)

For exploratory or long-running work, use `terminal(pty=true)`:

```bash
claude            # interactive TUI
codex             # interactive
opencode          # interactive TUI
```

Keep the session alive and submit follow-ups via `process(action='submit')`.

### 3. PR reviews

```bash
# Review the current diff
git diff origin/main...HEAD | claude -p "Review this diff for bugs and style issues"

# Or in-repo
gh pr diff 123 | codex exec "Review PR 123 for correctness and security issues"
```

### 4. Parallel work

Dispatch independent tasks to different agents in parallel background
processes, then collect and integrate:

```bash
terminal(background=true)  # claude -p "task A"
terminal(background=true)  # codex exec "task B"
# wait, collect, review both diffs, integrate
```

## Agent-Specific Notes

### Claude Code
- **Auth**: `claude login` (Anthropic account / API key)
- **Headless**: `claude -p "..."` — add `--output-format json` for structured results
- **Sandboxing**: `--permission-mode` controls what it may execute
- **Pitfall**: interactive sessions need a real TTY; `pty=true` or tmux

### Codex CLI
- **Auth**: `codex login` (ChatGPT account or API key)
- **Headless**: `codex exec "..."` (non-interactive)
- **Pitfall**: `codex exec` runs in a sandbox by default; pass `--dangerously-bypass-approvals-and-sandbox` only for trusted repos

### OpenCode
- **Auth**: `opencode auth login` (provider-agnostic — OpenAI, Anthropic, Ollama, etc.)
- **Headless**: `opencode run "..."` with `-m <model>` to pick the model
- **Pitfall**: model choice matters — a weak model produces weak code; pin the model for reproducible results

## Pitfalls (all agents)

- ❌ **Interactive CLI without PTY** — hangs forever waiting for input. Use `pty=true` or headless mode.
- ❌ **Unreviewed agent output** — never merge what you didn't review. Diff before commit.
- ❌ **Agent editing files outside scope** — give narrow prompts with explicit file paths; inspect `git diff` for scope creep.
- ❌ **Repeating work the agent already did** — check `git status` before starting; the agent may have left partial work.
- ❌ **Secrets in prompts** — never pass API keys or tokens in the task text.

## Verification Checklist

```bash
# After any agent task:
git status                # what changed
git diff --stat           # scope of changes
git diff | head -200      # review the actual diff
# Run the relevant tests before integrating
```

## Related
- `claude-code` — Claude Code deep-dive
- `codex` — Codex CLI deep-dive
- `opencode` — OpenCode deep-dive
- `hermes-agent` — the platform these run under
- `github-code-review` — reviewing agent PRs
