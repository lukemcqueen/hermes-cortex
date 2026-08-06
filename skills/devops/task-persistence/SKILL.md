---
name: task-persistence
version: 2.0.0
category: devops
description: Cross-session tasks via task-db.py or task_* MCP tools.
author: Hermes Cortex
platforms: [linux, macos]
aliases: [todo-persistence]
metadata:
  hermes:
    tags: [task, persistence, session, postgres, tasks, protocol, todo]
    related_skills: [session-manager, agent-fundamentals, task-start, session-start-discipline]
---

# Task Persistence — Cross-Session Task Tracking (tasks schema)

## Why This Exists

The Hermes `todo()` tool is **per-session** — items set in one session vanish
when the next starts. This skill documents the durable task system on the
`tasks` schema of each host's mycortex-postgres (party-reviewed design 2026-08-06:
docs/design/task-workflow.md).

**History:** the old system (bus.todos + todo-db.py) was retired 2026-08-06 —
`bus.todos` never existed on workers (bus schema is orchestrator-only), and
todo-db.py silently no-op'd (stdin-mode psql rc=0). The tasks schema is
applied on EVERY host by cortex-update.sh via the version-gated runner.

## Architecture

```
Agent Session
     │
     ├── todo()  ──►  ephemeral (Hermes tool, per-session)
     │
     └── task-db.py  ──►  tasks.tasks (per-host mycortex-postgres)
                │             │
                ├─ CLI        ├─ RLS per-profile isolation (fail-closed)
                └─ task-mcp.py├─ CRUD as mycortex_reader_<profile> (never superuser)
                  (MCP tools) └─ Survives crashes, restarts, disconnects
```

### Database

- **Schema:** `ops/services/tasks/schema/v00X__*.sql` (version-gated by
  `tasks.schema_version`; applied by `ops/services/tasks/migrate.py`)
- **Table:** `tasks.tasks` (active), `tasks.task_archive` (historical)
- **Functions:** `tasks.task_upsert()`, `tasks.task_list()`,
  `tasks.task_archive_old()`, `tasks.task_prune()`
- **RLS:** personal rows visible to own profile only; fleet rows visible to
  all, writable only by fleet writers (orchestrator profiles); fleet ×
  client-project and path/email/IP content banned (PII scrub gate)

### CLI + MCP

- **Deployed to:** `~/.hermes-cortex/scripts/task-db.py` (register in cortex-update.sh)
- **MCP server:** `mcp-servers/task-mcp.py`, registered as `todos`
  (tools: task_add, task_list, task_pending, task_update, task_save_end,
  task_prune). All agents — not orchestrator-only.

## Commands

```bash
# List my tasks (union of personal + locally-present fleet rows)
task-db.py list

# List with filters
task-db.py list --status pending
task-db.py list --project hermes-cortex --repo hermes-cortex

# Add a task (tag it: project/repo/scope/source)
task-db.py add "Fix dashboard health check" --priority 2 \
    --project hermes-cortex --repo hermes-cortex --scope personal --source manual

# Update status (canonical lifecycle; sets column=done on completed)
task-db.py update <uuid> --status in_progress
task-db.py update <uuid> --status completed

# Session start: print pending as JSON for todo() restore
task-db.py pending

# Bulk restore from JSON (session start)
task-db.py restore <pending.json>

# Session end: archive completed/cancelled, report remaining
task-db.py save-end

# Prune archived rows older than N (never touches active rows)
task-db.py prune --older-than 90d

# Apply schema (delegates to ops/services/tasks/migrate.py as DB owner)
task-db.py --apply-schema
```

## Session Protocol

### Session Start

1. `todo()` — load in-memory state (usually empty)
2. `task-db.py pending` — query DB for your profile's pending items (JSON)
3. If items exist, restore them: `todo(todos=<json_items>, merge=true)`

### Throughout Session

- Before each `begin_change()`: `task-db.py update <id> --status in_progress`
- After each `end_change()`: `task-db.py update <id> --status completed`

### Session End

- `task-db.py save-end` — archives completed/cancelled items
- Remaining `pending`/`in_progress` items persist in DB for next session

## Honest Fleet Semantics (party B-3)

`--scope fleet` stores the row **locally on this host only** — it is NOT
visible fleet-wide until transport ships (roadmap: git-backed, private repo).
The CLI prints this warning. Never claim fleet-wide visibility in reports.

## Security Invariants (party B-1/B-2)

- Identifier-ish values (agent/project/repo/target/assignee/scope/status/
  source/column) are allowlist-validated BEFORE use; all DML funnels through
  the parameterized `tasks.task_upsert()` — never string-built WHERE clauses.
- Free text is quote-doubled into string literals only.
- psql runs with `ON_ERROR_STOP=1`; query flows via STDIN, never embedded in
  a shell command string (the old sg-embedding path was shell-RCE).
- CRUD connects as `mycortex_reader_<profile>` — NEVER superuser.

## Anti-Patterns

- ❌ **Relying only on `todo()` tool** — per-session. Items vanish.
- ❌ **Using a local file for persistence** — the DB is already there.
- ❌ **Letting completed items accumulate** — run `task-db.py save-end`.
- ❌ **Forgetting to update status** — stale pending items clutter restore.
- ❌ **Hardcoding UUIDs** — retrieve via `task-db.py pending`/`list`.
- ❌ **Using bus.* or todo-* nomenclature** — the tasks system is `tasks.*`,
  `task-db.py`, `task_*` tools everywhere (AC-1).

## Known Issues

### ✅ FIXED 2026-08-06 — silent failure class (rc=0 stdin bug)

The old todo-db.py printed ✅ while rows vanished (stdin-mode psql returns
rc=0 on SQL error; bus.todos never existed on the migrated DB). The rewrite
uses `-c`/ON_ERROR_STOP + stderr scan; errors exit 1 with evidence. The
doctor now runs a **write-probe** (seed → list → archive) to catch the
"valid JSON but dead table" class — see `check_task_db`.

## Reference

- Design: `~/hermes-cortex/docs/design/task-workflow.md`
- CLI: `~/hermes-cortex/ops/scripts/manage/task-db.py`
- MCP: `~/hermes-cortex/mcp-servers/task-mcp.py`
- Migration runner: `~/hermes-cortex/ops/services/tasks/migrate.py`
- psql pitfalls: skill `psql-automation`
- Session restore: skill `session-start-discipline`
