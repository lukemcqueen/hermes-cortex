# todo-db.py Quick Reference

## Session Lifecycle

```
START ─► todo() + todo-db.py pending  ──►  todo(todos=[...], merge=true)
  │
  ├─► begin_change ─► todo-db.py update <id> --status in_progress
  ├─► end_change   ─► todo-db.py update <id> --status completed
  │
END   ─► todo-db.py save-end
```

## Commands

| Action | Command | Notes |
|--------|---------|-------|
| List mine | `todo-db.py list` | Defaults to $AGENT_NAME |
| List fleet | `todo-db.py list --agent esther` | Any agent's todos |
| Filter by status | `todo-db.py list --status pending` | Or in_progress/completed |
| Add | `todo-db.py add "content" --priority 2` | Priority 0=default |
| Start working | `todo-db.py update <uuid> --status in_progress` | Before begin_change |
| Complete | `todo-db.py update <uuid> --status completed` | After end_change |
| Cancel | `todo-db.py update <uuid> --status cancelled` | If task abandoned |
| Session start | `todo-db.py pending` | JSON output for restore |
| Session end | `todo-db.py save-end` | Archives completed, reports pending |

## Common Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `sg: command not found` | sg docker wrapper not installed | Use direct psql or check docker group |
| `ERROR: relation "bus.todos" does not exist` | Schema not applied | Run: `sg docker -c "docker exec -i gbrain-postgres psql -U gbrain -d gbrain" < ~/hermes-cortex/core/cortex_bus/schema/todos.sql` |
| `Permission denied` on sg docker | User not in docker group | `sudo usermod -aG docker $USER && newgrp docker` |
| todo-db.py not found | cortex-update.sh hasn't run | `cd ~/hermes-cortex && bash cortex-update.sh` |
