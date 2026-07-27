# Todo Persistence — Design & Migration Notes

## Origin

2026-07-21: User discovered that `todo()` tool is per-session. The previous session
had been worked through reactively (user commands like "pull latest", "fix this cron")
without creating any todo items. When the next session started, `todo()` returned empty.

**User:** "Todo items should have been saved across sessions."

## First Attempt — Local JSON File

I created `~/.hermes-cortex/state/session-todo.json` — a flat file to persist todo
items. Patched SOUL.md P37 and task-start skill to read/write it.

**User's response:** "How about todos being saved in our bus as workflow items?
Each agent can have their own persistent todos. Or separate db."

**Correction:** Using shared infrastructure (already-running Postgres) over a local
file hack. The bus/Postgres is already deployed, ACID, fleet-visible.

## Final Design — bus.todos (gbrain Postgres)

### Key Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Storage | Postgres (bus.todos) | Already running, shared, ACID |
| Table schema | Generalized (any agent) | `agent_name` column for per-agent scoping |
| CLI tool | Python script `todo-db.py` | Uses `sg docker` for psql access |
| Schema table migration | `CREATE TABLE IF NOT EXISTS` | Safe to re-apply, auto-migrates |
| Archive pattern | `bus.todo_archive` table | Completed items moved here, keeps active table lean |
| Session restore | `todo-db.py pending → JSON → todo()` | Bridge between DB and ephemeral Hermes tool |

### Schema

```sql
CREATE TABLE IF NOT EXISTS bus.todos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
        CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    session_id      TEXT,
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bus.todo_archive (
    id              UUID PRIMARY KEY,
    agent_name      TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL,
    session_id      TEXT,
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    archived_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Functions

- `bus.todo_upsert(p_id, p_agent_name, p_content, p_status, p_session_id, p_priority)` — upsert a todo
- `bus.todo_list(p_agent_name, p_status)` — filtered listing
- `bus.todo_archive_old(p_agent_name)` — move completed/cancelled to archive

### Todo Status Flow

```
pending ──► in_progress ──► completed
                              │
  pending ────────► cancelled ┘
```

### Verification

Tested end-to-end:
1. Created a todo via `todo-db.py add`
2. Verified via `todo-db.py list` and `todo-db.py pending`
3. Updated status via `todo-db.py update`
4. Confirmed persistence across PIDs
5. Confirmed fleet visibility (any agent can `list --agent moses`)
6. Confirmed doctor HEALTHY after deployment

### Commits

```
[6cf8e29] feat: add persistent todo storage v2 bus.todos table
  3 files: schema/todos.sql, todo-db.py, moses/SOUL.md

[70c52c7] chore: register todo-db.py in cortex-update.sh
  1 file: cortex-update.sh (+1 line)
```

## Overlapping Skills

These skills also touch the todo/session lifecycle territory:

- **task-start** — Step 1 already updated this session to check bus.todos
- **session-manager** — §3 (Progress Tracking) covers inline lists, §5 added cross-session
- **agent-fundamentals** — §6 (Load Context) mentions `todo()` but not persistence

The `session-manager` and `agent-fundamentals` skills are `created_by=None`
(not agent-created), so they couldn't be patched in this session. The
`todo-persistence` skill fills the gap.

## Future Notes

- Consider adding a `todo-db.py watch` command that polls for changes
- Consider adding deadline/reminder support via cron integration
- Consider bus-based notification when another agent updates a shared todo
