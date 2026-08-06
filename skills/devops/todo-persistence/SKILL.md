---
name: todo-persistence
version: 1.0.0
category: devops
description: >-
  Cross-session todo persistence using the shared gbrain Postgres DB.
  Covers the bus.todos table, todo-db.py CLI, session start/end protocol,
  and fleet-visible todo management. Replaces ephemeral per-session
  todo() tool with durable Postgres storage.
author: Hermes Cortex
platforms: [linux]
metadata:
  hermes:
    tags: [todo, persistence, session, bus, postgres, protocol]
    related_skills: [session-manager, agent-fundamentals, task-start, cortex-bus]
---

# Todo Persistence — Cross-Session Task Tracking

## Why This Exists

The Hermes `todo()` tool is **per-session** — items set in one session vanish when the next starts. This skill documents the durable, fleet-visible todo system built on top of the shared gbrain Postgres (bus.todos table).

**What happened without it:** The last session's work had no todo items saved. The next session started with an empty list and the user had to remind me. The fix was building DB-backed persistence.

## Architecture

```
Agent Session
     │
     ├── todo()  ──►  ephemeral (Hermes tool, per-session)
     │
     └── todo-db.py  ──►  bus.todos (gbrain Postgres, persistent)
                                │
                                ├── All agents see each other's todos
                                ├── SQL-queryable
                                └── Survives crashes, restarts, disconnects
```

### Database

- **Schema:** `core/cortex_bus/schema/todos.sql`
- **Tables:** `bus.todos` (active), `bus.todo_archive` (historical)
- **Functions:** `bus.todo_upsert()`, `bus.todo_list()`, `bus.todo_archive_old()`
- **Auto-applied by:** `cortex-update.sh` (uses `CREATE TABLE IF NOT EXISTS`)

### CLI Tool

- **Deployed to:** `~/.hermes-cortex/scripts/todo-db.py`
- **Registered in:** `cortex-update.sh` register() map
- **All agents** get it on next `cortex-update.sh`

## Commands

```bash
# List my todos (defaults to current agent)
todo-db.py list

# List another agent's todos (fleet visibility)
todo-db.py list --agent esther

# Filter by status
todo-db.py list --status pending
todo-db.py list --status in_progress

# Add a new todo
todo-db.py add "Fix dashboard health check" --priority 2

# Update status (every change cycle)
todo-db.py update <uuid> --status in_progress
todo-db.py update <uuid> --status completed
todo-db.py update <uuid> --status cancelled

# Session start: print pending as JSON for todo() restore
todo-db.py pending

# Session end: archive completed, report remaining
todo-db.py save-end
```

## Session Protocol

### Session Start

1. `todo()` — load in-memory state (usually empty)
2. `todo-db.py pending` — query DB for your agent's pending items
3. If items exist, restore them: `todo(todos=<json_items>, merge=true)`

### Throughout Session

- Before each `begin_change()`:
  - `todo-db.py update <id> --status in_progress`
  - `todo(todos=..., merge=true)` to sync in-memory tool
- After each `end_change()`:
  - `todo-db.py update <id> --status completed`

### Session End

- `todo-db.py save-end` — archives completed/cancelled items
- Remaining `pending`/`in_progress` items persist in DB for next session
- If all items complete, the DB is clean and save-end is a no-op

### Fleet Viewing

```bash
# Check what other agents are working on
todo-db.py list --agent titus --status pending
todo-db.py list --agent esther
todo-db.py list --agent joseph --status in_progress
```

## Why DB Over File

| Criterion | Local JSON file | Postgres table |
|-----------|----------------|----------------|
| Persistence | Yes | Yes (better) |
| Fleet-visible | No | Yes |
| Concurrent access | Race-prone | ACID |
| SQL queries | No | Yes |
| Admin UI | No | psql |
| New infra | No (just a file) | No (already running) |

**The rule:** If the database is already running and all agents have access, use it. A file is never better than a table when the DB exists.

## Anti-Patterns

- ❌ **Relying only on `todo()` tool** — it's per-session. Items vanish on disconnect or timeout.
- ❌ **Using a local file for persistence** — the DB is already there, available, shared, and better.
- ❌ **Letting completed items accumulate** — run `todo-db.py save-end` each session to keep the table lean. The archive function handles this.
- ❌ **Forgetting to update status** — stale `pending` items from old sessions clutter the restore step. If a session ended abruptly, clean up stale items on next start.
- ❌ **Hardcoding UUIDs** — never hardcode a todo UUID. Always retrieve it via `todo-db.py pending` or `todo-db.py list`.

## Known Issues

### ✅ FIXED 2026-08-06 — `todo-db.py` silent failure (stdin/rc bug)

Previously `todo-db.py update` (and every command) printed ✅ even when the
SQL never reached Postgres: stdin-mode psql returns rc=0 on SQL failure, so
errors were swallowed. Also, `bus.todos` never existed on the migrated
mycortex-postgres — every add was a silent no-op.

**Fix (Esther, 2026-08-06, commit `379a6e39`):**
- psql() now uses `-c` mode via direct `docker exec` (rc propagates) with
  an `sg docker -c` fallback that embeds the query in the command string
- `todo-db.py --apply-schema` applies `core/cortex_bus/schema/todos.sql`
  idempotently (platform-aware: docker exec on Linux, direct psql via
  mycortex.conf on macOS); cortex-update.sh runs it every update
- Errors now exit 1 with stderr — no more silent ✅
- The dream→todo bridge (`dream-todo-bridge.py`) builds on this:
  docs/design/mycortex-dream-todo-bridge.md

**If a command still fails silently:** run `todo-db.py list` and check it
against psql directly:

---

## Reference

- Schema: `~/hermes-cortex/core/cortex_bus/schema/todos.sql`
- CLI: `~/hermes-cortex/ops/scripts/manage/todo-db.py`
- SOUL.md Principle 37: Session Todo Protocol — With Persistent DB Storage
- bus.todos shares the gbrain Postgres instance with the Agent Bus (PGMQ)
