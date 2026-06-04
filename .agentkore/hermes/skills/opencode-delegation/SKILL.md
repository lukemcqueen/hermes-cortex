---
name: opencode-delegation
description: How to spawn OpenCode subagents and verify their results.
---

# OpenCode Delegation

## When to delegate
A task qualifies for OpenCode delegation when it involves:

- Code changes spanning 3+ files
- Running build/test pipelines via `./run`
- Solving bugs that need iterative test-debug loops
- Refactoring that touches multiple modules
- Any operation that benefits from OpenCode's permission pre-approval (`./run *`)

## Context packaging
Pass these in `delegate_task(context=...)`:

```
Project structure: key dirs, config files
Files involved:   exact paths
Error context:    error messages, logs
Constraints:      "use ./run test, match repo style, no reformatting"
Target:           model notes if relevant
```

## Task definition format

```
Goal: implement X in file Y
Context:
  - Files: src/file_a.go, src/file_b.go
  - Constraint: validate with `./run test`, keep style
Toolsets: terminal, file, search
```

## Result verification
Subagent summaries are self-reports — always verify:
- Stat the modified files (they exist)
- Read back critical changes
- Run `./run test` to validate
- Check expected behavior with a direct tool call

## OpenCode notes
- Pre-approved commands: `./run *`
- Timeout: 180s default via opencode run; use delegate_task for longer
- Skills live at `.opencode/skills/<name>/SKILL.md`
- Permission model in `opencode.json` — don't override
