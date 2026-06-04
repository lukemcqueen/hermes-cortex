---
name: agent-flow
description: |
  Route tasks through the smallest safe workflow. One flow per task.
  Triggers: "agent flow", "what workflow", "run agentkore", "start task", "continue task", "full workflow"
---

# Agent Flow

## Core Rule

Use the lightest workflow that safely completes the task.

```
simple → fast path | unclear → elicit first | large → PRD/tasks/session | risky → review/security/release
```

## Start Protocol

1. `agent-contract`
2. `repo-discovery` if repo unfamiliar
3. `git-workflow` before edits
4. `state-orchestrator` if context/session/docs may matter
5. Choose one flow below. Execute immediately — no pausing after plan.

Stop only when: task complete | user asked for plan-only | destructive approval needed | verification can't run | failure unsafe | requirement impossible | tool missing

## Flows

### A: Simple Code Change
Small bug fix, one-file refactor, small edit
```
agent-contract → git-workflow → relevant skill → change-test-loop → code-review
```

### B: Unclear Requirements
Fuzzy feature, incomplete scope
```
ak-elicit → fast-bmad → story-slicing → prd-lite (if needed)
```

### C: Enterprise Feature
Multi-file, auth/data/API, high-risk, architecture impact
```
doc-system → ak-elicit → ak-party → prd-lite → story-slicing → prd-to-tasks → session-manager → task-executor → change-test-loop → code-review → security → release-checklist
```

### D: Debugging
Failing test, runtime error, broken tool
```
debugging → change-test-loop → code-review
```
If production impact: `incident-debug` → `security` → `memory-management`

### E: API / Backend
Endpoint, contract, auth, service boundary
```
api-design → relevant skill → testing-strategy → change-test-loop → security → code-review
```
Add `database-migrations` if schema changes, `postgres` if query/index work.

### F: Database
Schema, migration, backfill, indexes
```
database-migrations → postgres → testing-strategy → change-test-loop → security → release-checklist
```
Include rollback plan. Verify lock/data risk. Separate data + schema when risky.

### G: UI
Visual or component work
```
ui → ui-strategy → framework skill → testing-strategy → change-test-loop → design-check → code-review
```
Add `playwright-browser` if E2E needed.

### H: Proxy / Local LLM
Go proxy, tool calling, context, RAG/chunking
```
local-llm-reliability → proxy-enforcer → proxy-tool-calling → go-lang → testing-strategy → change-test-loop → security
```
Never assume RAG exists. Validate tool I/O. Test malformed inputs.

### I: Docs
PRDs, ADRs, task plans, architecture notes, research
```
doc-system → memory-management (if durable insight learned)
```

### J: Release
Before merge/deploy
```
git-workflow → code-review → security (if risk exists) → release-checklist → memory-management
```

### K: Session Continuity
Save, restore, or continue work
```
state-orchestrator → session-manager → task-executor (if task plan exists)
```
Verify session against repo. Keep concise. No long doc duplication.

### L: Skill / System Update
When changes affect `skills/`, `commands/`, `AGENTS.md`, `config/`, `registry/`, `scripts/`
```
skill-registry-maintainer → release-checklist
```
Update primary path → sync mirrors → update registries → update AGENTS.md → update agent-flow if routing changes → update commands → remove stale refs → run validation.

## Decision Shortcuts

```
Need clarity?          → ak-elicit
Need architecture?     → ak-party
Need implementation?   → task-executor
Need bug fix?          → debugging
Need verification?     → testing-strategy
Need security review?  → security
Need release check?    → release-checklist
Need continuity?       → session-manager
Changing skills?       → skill-registry-maintainer
```

## Budget

Simple: 3–5 skills | Enterprise: 6–9 | Avoid loading everything.

## Anti-Patterns

Enterprise flow for tiny fixes | coding before inspecting | skipping tests | creating docs without discovery | saving everything to memory | multi-tasking | hiding uncertainty | simulating | changing skills without updating registry/AGENTS.md/commands | leaving stale skill names in AGENTS.md or commands
