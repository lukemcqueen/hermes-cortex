# Alembic migration cycle fix

A merge revision listing a future revision as a parent head creates a cycle in the migration graph, preventing `alembic upgrade head` from running.

## Diagnostic

The API entrypoint logs show:

```
FAILED: Cycle is detected in revisions (001, 002_add_works_publisher_id, 002, ...)
```

along with a list of every revision in the graph.

## Root cause

The merge file (`s4_merge_all_heads.py` in acme-works) had this structure:

```python
down_revision: tuple[str, ...] | None = (
    "002_add_works_publisher_id",    # OK — branch A head
    "003_add_user_settings",          # OK — branch B head
    "a1b2c3d4e5f6",                  # OK — branch C head
    "5071fe43e098",                  # BUG — this revision is AFTER the merge in the chain
)
```

The actual revision chain was:

```
s4_merge_all_heads → d1d107cafdc3 → 5071fe43e098
```

Listing `5071fe43e098` as a parent of `s4_merge_all_heads` when `5071fe43e098` descends from `s4_merge_all_heads` creates a cycle.

## Fix

Remove the future revision from the merge's `down_revision` tuple. The three actual branch heads at the time of the merge were:

```python
down_revision: tuple[str, ...] | None = (
    "002_add_works_publisher_id",
    "003_add_user_settings",
    "a1b2c3d4e5f6",
)
```

## Prevention

- Never manually author merge revisions. Use `alembic merge heads -m "description"` to generate them — Alembic only lists actual heads at the time.
- Run `alembic check` locally and in CI after any migration change to detect cycles before they hit production.
- The `./run check:migrations` command runs `alembic check` inside the Docker API container against the live database (catches schema drift + graph issues).
- The static checker `./run check:alembic` (`scripts/check-alembic-heads.py`) checks for multiple heads and long revision IDs from migration file metadata (does NOT require a database).
