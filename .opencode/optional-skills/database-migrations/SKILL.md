---
name: database-migrations
description: |
  Plan and execute safe database migrations with minimal lock time,
  reversible steps, backfills, and verified rollbacks for production systems.

  Triggers when user mentions:
  - "migration"
  - "db change"
  - "schema update"
  - "add column"
  - "backfill"
  - "index"
---

# Database Migrations

## Purpose
Make schema and data changes that are:
- safe in production
- reversible when possible
- low-lock / low-risk
- compatible with live traffic

---

## Output (STRICT ORDER)

1. **Migration Plan**
2. **SQL / Migration Code**
3. **Verification / Rollback**

---

## Core Rule

Never block production or risk data loss.

Prefer multi-step, reversible migrations over single risky changes.

---

## Migration Types

- `schema` → columns, tables, indexes
- `data` → backfills, transformations
- `hybrid` → both (split when risky)

---

## Safe Migration Workflow (STRICT)

1. Identify change type
2. Assess table size and traffic
3. Choose safe strategy (single vs multi-step)
4. Separate schema and data if needed
5. Apply minimal change first
6. Backfill gradually if required
7. Add constraints after data is valid
8. Verify
9. Ensure rollback path

---

## Safe Patterns

### Add Column (Large Table)

```sql
-- Step 1: add nullable column
ALTER TABLE users ADD COLUMN timezone text;

-- Step 2: backfill (outside migration, batched)

-- Step 3: enforce constraint later
ALTER TABLE users
ADD CONSTRAINT users_timezone_not_null
CHECK (timezone IS NOT NULL);
```

---

### Add Index (Production Safe)

```sql
CREATE INDEX CONCURRENTLY index_orders_on_user_id
ON orders (user_id);
```

Rules:

* use CONCURRENTLY for large tables
* never block writes

---

### Rename / Replace Column (Safe)

```txt
old_column → new_column (dual-write)
→ backfill
→ switch reads
→ remove old column later
```

---

## Backfill Rules

* run outside main migration when large
* process in batches
* avoid long transactions
* monitor performance
* allow pause/resume

---

## Constraints

Add constraints only after data is valid:

* NOT NULL
* UNIQUE
* FOREIGN KEY

Prefer phased approach:

1. validate data
2. add constraint
3. enforce at app level

---

## Lock Safety

Avoid:

* full table rewrites
* long transactions
* blocking writes

Check:

* table size
* index build time
* lock level

---

## Rollback Rules (MANDATORY)

Every migration must define:

* how to revert schema
* how to handle partial data changes
* whether rollback is safe or destructive

Example:

```sql
DROP INDEX CONCURRENTLY index_orders_on_user_id;
```

---

## Data Safety

Before running:

* run SELECT to estimate impact
* verify row count
* test on staging or subset

Never:

* run destructive updates blindly
* combine schema + large data change in one step
* assume data consistency

---

## Verification

```txt
migration applied successfully
→ schema matches expectation
→ queries still work
→ no performance regression
→ app tests pass
```

Optional:

```sql
EXPLAIN (ANALYZE, BUFFERS) <query>;
```

---

## Testing Rules

Test:

* migration up
* migration down (if reversible)
* data integrity after migration
* application compatibility

---

## Deployment Strategy

For risky changes:

```txt
deploy 1: additive change
deploy 2: app reads new field
deploy 3: remove old field
```

Never break running app between deploys.

---

## Anti-Patterns

Avoid:

* `NOT NULL DEFAULT` on large tables (locks)
* blocking index creation
* massive updates in one transaction
* mixing schema + heavy data change
* no rollback plan
* deleting columns immediately
* unverified assumptions about data

---

## Final Report

```md
## Migration Result
safe | needs changes | high risk

## Change
- schema:
- data:

## Safety
- lock risk:
- backfill:

## Verification
- commands:

## Rollback
- steps:

## Notes
Risks, follow-ups
```

---

## Goal

Deliver safe, incremental, production-ready migrations that:

* avoid downtime
* protect data
* support continuous deployment