--- Full content (truncated) ---
---
name: antigravity-cli
description: "Operate the Antigravity CLI (agy): plugins, auth, sandbox."
version: 0.1.0
author: Tony Simons (asimons81), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Antigravity, CLI, Auth, Plugins, Sandbox]
    related_skills: [grok, codex, claude-code, hermes-agent]
---

# Antigravity CLI (`agy`)

Operator guide for the Antigravity CLI, invoked as `agy`. Run all `agy`
commands through the Hermes `terminal` tool; inspect its config and logs with
`read_file`. This skill is reference + procedure — it does not wrap a network
API, so there is nothing to authenticate from Hermes itself.

## When to Use

- Installing, updating, or smoke-testing the `agy` binary
- Driving non-interactive `agy --print` / `agy -p` one-shots
- Debugging Antigravity auth, sandbox, permissions, or plugin state
- Reading Antigravity settings, keybindings, conversations, or logs

## Mental model

Antigravity has two layers — kee
... [truncated]
--- End skill ---