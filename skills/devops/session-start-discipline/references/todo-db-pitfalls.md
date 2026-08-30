# todo-db.py Pitfalls

## Silent-Failure Bug in `update` Command

The `todo-db.py update <uuid> --status <state>` command prints
`✅ Todo <uuid>... → <state>` even when the SQL fails silently.

**Root cause:** The `DB_QUERY` uses `sg docker -c "docker exec -i psql ..."`
which wraps the command in a shell. The `subprocess.run(input=full_query, ...)`
sends the SQL via stdin to the SHELL (sg), not directly to psql. The shell
consumes stdin, so psql never sees the SQL, and no rows are updated.

**Detection:** If a todo's status doesn't change after `update`:
1. Check the DB directly:
   ```bash
   psql() { sg docker -c "docker exec -i gbrain-postgres psql -U gbrain -d gbrain -t -A -F '||'" <<< "$1"; }
   psql "SELECT content, status FROM bus.todos WHERE id='<uuid>'::uuid;"
   ```
2. Or skip todo-db.py update entirely and use direct SQL:
   ```bash
   sg docker -c "docker exec -i gbrain-postgres psql -U gbrain -d gbrain -t -A" <<SQL
   UPDATE bus.todos SET status = 'completed', updated_at = now()
   WHERE id = '<uuid>'::uuid;
   SQL
   ```

**Workaround for `save-end`:** The archive function `bus.todo_archive_old()`
works correctly when the status was already set to `completed` in the DB.
The issue is only in the `update` step, not the `save-end` step.

**Status:** Known issue. The `DB_QUERY` in `todo-db.py` needs to pipe the
query differently so `sg` doesn't eat stdin.
