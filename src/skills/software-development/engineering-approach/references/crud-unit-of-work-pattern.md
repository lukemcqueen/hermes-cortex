# CRUD Unit-of-Work Pattern

Remove `db.commit()` and `db.refresh()` from CRUD methods, pushing transaction management to callers.

## Problem

CRUDBase's `create()`, `update()`, `delete()` call `await db.commit()` internally. This prevents:
- Transactional composition (can't combine multiple CRUD ops in one transaction)
- Audit log wiring (commit happens before the audit record is written)
- Rollback (an error in a caller after commit() can't be undone)

## Solution

### 1. Remove internal commits from CRUD

In `app/crud/base.py`:

```python
async def create(self, db: AsyncSession, **kwargs) -> ModelType:
    obj = self.model(**kwargs)
    db.add(obj)
    # NO db.commit() — caller manages transaction
    return obj  # Uncommitted — caller calls db.refresh() if needed
```

Add the same docstring to every CRUD method: `"""Does NOT commit — caller must manage transaction."""`

Apply to:
- `base.py`: `create()`, `update()`, `delete()`
- Overridden `create()` in `publisher.py`, `work.py`, `creator.py`, `society.py`, `member.py`, `lookup.py`, `registration_candidate.py`, `webhook.py`
- `approve()`/`reject()` in `registration_candidate.py`
- `mark_delivered()`/`mark_failed()` in `webhook.py`

### 2. Find all callers

Search for CRUD method calls across:
- `app/routers/` — standard API endpoints
- `app/mcp/` — MCP tool implementations
- `app/services/` — service layer files
- `app/routers/integrations.py` — integration endpoints

Use `search_files` to find `crud_` or `CRUD` usage, then check each for missing `db.commit()`.

### 3. Add commits to callers

Each caller that calls a CRUD create/update/delete must now add:
```python
await db.commit()
await db.refresh(obj)  # if the caller needs the auto-generated id/timestamps
```

**Standard routers:** Most routers already call `await db.commit()` after the CRUD + audit call. They just lost the redundant double-commit — no change needed.

**MCP tools:** Check `app/mcp/tools/__init__.py` for CRUD calls that create/update records. Add `await db.commit()` after the CRUD call and before returning.

**Services:** Check `app/services/` for CRUD calls in background tasks or delivery workers. Add commits at natural transaction boundaries.

**Edge case — integration routers:** Files like `integrations.py` that use `approve()`/`reject()` from `registration_candidate.py` may need a single `commit()` + `refresh()` after the if/elif/else block instead of the old pattern where each branch committed internally.

### 4. Verify

```bash
python -c "from app.crud.base import CRUDBase; print('OK')"
python -c "from app.routers import works, contracts, members, ...; print('OK')"
python -m pytest tests/ -x -q -k "test_list or test_create"
```
