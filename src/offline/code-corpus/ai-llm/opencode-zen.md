---
language: yaml
tags: [hermes, agent, opencode, coding, tool]
title: OpenCode — Hermes Coding Subagent
description: Using OpenCode CLI as a delegable coding subagent from Hermes for PR review, feature implementation, and batch analysis.
source: pattern
---

```yaml
# OpenCode is the coding subagent that Hermes delegates to for
# code-intensive tasks. Configured in Hermes config.yaml:
#
# opencode:
#   enabled: true
#   model: deepseek-v4-flash
#   provider: opencode-zen

# ── Typical delegation from Hermes ──
# Hermes delegates to OpenCode for:
#   - Feature implementation (complex multi-file changes)
#   - PR review (full codebase context)
#   - Bug fixes that span multiple files
#   - Refactoring with test coverage
```

```bash
# ── OpenCode CLI direct usage ──
opencode "Add a rate limiter middleware to the FastAPI app"

# ── PR review mode ──
opencode --review --diff <(git diff main)

# ── Batch processing ──
opencode --batch "Run flake8 on all files and fix issues"

# ── With specific model ──
opencode --model deepseek-v4-flash "Explain this codebase architecture"

# ── Integration ──
# OpenCode is spawned as a subagent when Hermes hits the
# `delegate_task` tool with a coding-heavy goal.
# Results return asynchronously — Hermes continues working.
```

```python
# Programmatic usage via Hermes delegate_task
# (this is what Hermes does internally)
"""
delegate_task(
    goal="Implement user authentication endpoints",
    context="FastAPI app at /path/to/project",
    role="leaf",
    toolsets=["terminal", "file"]
)
# Subagent (OpenCode) runs independently
# Results re-enter conversation when done
"""
```
