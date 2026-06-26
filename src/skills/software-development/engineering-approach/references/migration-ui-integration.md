# Migration Scripts — UI Integration Pattern

## The Right Approach: Read-Only API → Existing UI

Bash migration scripts (`create-backup.sh`, `restore-backup.sh`) run on the
migration workspace filesystem. The FastAPI server is a separate process.
**Do not attempt to execute shell scripts from the API layer.** It requires
shell exec permissions, job queue, timeout handling, and auth guardrails —
significant new infra for marginal gain.

Instead, connect via the audit JSON the scripts already produce.

## Pattern: Audit JSON → Read-Only Endpoint → Existing Audit-Log UI

### What `restore-backup.sh` already writes

```json
{
  "completed": [
    {
      "timestamp": "2026-05-26T...",
      "actor": "ji-yeon",
      "reason": "Validation failed: divergence in work-level sums",
      "status": "success"
    }
  ]
}
```

### Step 1 — Create a read-only FastAPI endpoint

In `apps/api/routers/migration_audit.py`:

```python
from fastapi import APIRouter, Depends
from middleware.auth import require_s2s_auth
import json, os

router = APIRouter(
    prefix="/api/v1/migration",
    tags=["migration"],
    dependencies=[Depends(require_s2s_auth)]
)

AUDIT_PATH = os.getenv("MIGRATION_AUDIT_LOG", "./rollback/audit.json")

@router.get("/audit")
def get_migration_audit():
    """Read-only view of migration script audit events."""
    if not os.path.exists(AUDIT_PATH):
        return {"completed": [], "failed": []}
    with open(AUDIT_PATH) as f:
        return json.load(f)
```

### Step 2 — Register the router in `main.py`

```python
from routers.migration_audit import router as migration_audit_router
# ...
app.include_router(migration_audit_router)
```

### Step 3 — Add to `apps/web/src/lib/api.ts`

```typescript
export function listMigrationAuditEvents(): Promise<MigrationAuditEvents> {
  return fetchJSON('/migration/audit');
}
```

### Step 4 — Extend existing audit-log page to filter/display migration events

The existing audit-log page already shows `event_type`, `actor`, `timestamp`.
Add a filter or section for `event_type` matching `migration.restore` patterns.
No new UI component needed — reuse the existing table.

## Why Not Execute Scripts from the UI?

| Concern | Why It's a Problem |
|---|---|
| Shell exec from FastAPI | Requires `os.system` / `subprocess` — huge security surface |
| Async job handling | API worker blocks or needs a job queue (Celery, RQ, etc.) |
| Filesystem access | API server may not have access to migration workspace mount |
| Auth / authorization | Which users can trigger restore? Need a policy engine |
| Timeout / long-running | HTTP request timeout, worker lifecycle management |
| Idempotency | Two users clicking restore simultaneously |

The read-only approach avoids all of this. The scripts own the audit JSON;
the API just reads it. The UI just displays it.

## Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/migration/audit` | Read audit events from `./rollback/audit.json` |
| GET | `/api/v1/migration/status` | Backup timestamp, backup count, recent restore events |

Neither endpoint executes anything. Both are simple file reads with error
handling for missing files.

## Environment Variable

```bash
MIGRATION_AUDIT_LOG=./rollback/audit.json   # path to restore-backup.sh audit output
```

Set this in the API server's environment so it can find the audit file in the
migration workspace.