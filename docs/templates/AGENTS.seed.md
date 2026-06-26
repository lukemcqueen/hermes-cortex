<!--
  Hermes Cortex — Seeded AGENTS.md template
  Placeholders: {{PROJECT_NAME}} {{PROJECT_DESCRIPTION}} {{SEED_DATE}} {{SEED_COMMIT}}
-->
# Agent Guidelines — {{PROJECT_NAME}}

*Seeded from Hermes Cortex {{SEED_COMMIT}} on {{SEED_DATE}}*

Orientation for any agent working on this repo. See `.hermes-cortex/` for installed tooling.

---

## Project

{{PROJECT_DESCRIPTION}}

## Convention

`.hermes-cortex/` holds agent infra (hidden, near code). Agents check here first,
falling back to repo root if absent.

| Path | Purpose |
|------|---------|
| `.hermes-cortex/sessions/` | Session state (current.md + archive/) |
| `.hermes-cortex/memory/` | Per-dev MEMORY.md, USER.md (gitignored) |
| `.hermes-cortex/skills/` | Project-specific Hermes skills (tracked) |
| `AGENTS.md` | This file — agent orientation |

## Commands

```bash
./run up        # Start services
./run down      # Stop services
./run restart   # Restart services
./run logs      # Follow logs
./run build     # Build images
./run ps        # List running services
./run test      # Run tests (handles DB, env, permissions)
```

## Agent Contract

Non-negotiable rules for every agent in this repo:

1. Real execution — run actual commands, write real files, verify with tests.
2. Verified deliverables — exercise every change. A plan/stub is not done.
3. Fix root causes — check sibling paths for the same flaw.
4. Touch only what the task needs — no drive-by refactors.
5. Batch independent lookups — parallelize reads and searches.
6. Report blockers honestly — never fabricate output.
7. State confidence explicitly — say what you know vs what you assume.
8. Keep working until done — every response makes progress or delivers.
9. Use tools, not descriptions — every response has tool calls.
10. Score every change — every code/config/script change logs to loop-governance DB.
11. Tests/TDD are the default — RED-GREEN-REFACTOR. Only explicit opt-out bypasses.

## Loop Governance

Every change is scored by the loop-governance system:

**CLI (hooks/scripts):** `score-cycle --task <id> --cycle <N> --code-file <path> --pass-pct <rate>`
**CLI feedback:** `loop-feedback accept <id>` / `loop-feedback override <id> --note "reason"`

**MCP (agents):**
- `mcp_loop_governance_cache_search(query="...")`
- `mcp_loop_governance_cycle_query(task_id="...")`
- `mcp_loop_governance_feedback_accept(cycle_id=N)`

Non-negotiable: every commit must be scored.

---

## Project Notes

*(Add project-specific conventions, architecture, dev setup, testing, and deployment here.)*
