# AgentKore Routing

Use `agent-flow` to select the smallest safe workflow.

## Default route

```txt
agent-contract → agent-flow → selected skills → change-test-loop → review/report
```

## Common routes

- Simple code: `git-workflow` → stack skill → `change-test-loop` → `code-review`
- Unclear scope: `ak-elicit` → `fast-bmad` → `story-slicing`
- Enterprise feature: `doc-system` → `ak-elicit` → `ak-party` → `prd-lite` → `prd-to-tasks` → `task-executor`
- API/backend: `api-design` → stack skill → `testing-strategy` → `security`
- Database: `database-migrations` → `postgres` → `release-checklist`
- UI: `ui-strategy` → `tailwind`/`bootstrap`/framework → `design-check` → `playwright-browser` if E2E needed
- Proxy/local LLM: `local-llm-reliability` → `proxy-enforcer` → `proxy-tool-calling`
- Docs: `doc-system` (discovers, creates, links project docs)
- State: `state-orchestrator` → `session-manager` → `memory-management`

- Shell scripts: `bash-shell` → `testing-strategy` → `change-test-loop`
- Skill/system update: `skill-registry-maintainer` → `release-checklist`
