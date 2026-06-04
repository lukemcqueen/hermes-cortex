---
name: postgres
description: |
  Design, refactor, and optimize PostgreSQL schemas, queries, indexes,
  constraints, transactions, and safe migrations.

  Triggers when user mentions:
  - "postgres"
  - "sql query"
  - "database migration"
  - "index performance"
  - "query plan"
  - "transaction"
---

# PostgreSQL

## Purpose
Create safe, performant, production-ready PostgreSQL changes.

Use for:
- schema design
- migrations
- indexes
- constraints
- transactions
- query optimization
- JSONB
- full-text search

---

## Output (STRICT ORDER)

1. **SQL / migration code**
2. **Explanation** (≤3 sentences)
3. **Verification** (`EXPLAIN`, tests, or rollback notes)

---

## Workflow (STRICT)

1. Identify goal: schema, query, migration, performance, or data fix
2. Inspect existing schema/query patterns first
3. Prefer constraints for integrity
4. Add indexes only for real query patterns
5. Check lock risk for migrations
6. Use transactions for multi-step writes
7. Verify with real query plans when performance matters

---

## Schema Rules

- Use proper column types
- Prefer `NOT NULL` when required
- Use foreign keys for relationships
- Use check constraints for valid values
- Use unique constraints/indexes for uniqueness
- Avoid storing derived data unless justified

---

## Index Rules

Add indexes for:
- frequent filters
- joins
- sort/order clauses
- uniqueness
- partial filtered queries

Avoid:
- speculative indexes
- duplicate indexes
- indexing low-cardinality columns alone
- excessive indexes on write-heavy tables

Common patterns:

```sql
CREATE UNIQUE INDEX index_users_on_email ON users (lower(email));

CREATE INDEX index_orders_on_user_id ON orders (user_id);

CREATE INDEX index_orders_on_status_created_at
ON orders (status, created_at DESC);

CREATE INDEX index_orders_on_pending
ON orders (created_at DESC)
WHERE status = 'pending';
```

---

## Query Performance

Before claiming performance improvement, use:

```sql
EXPLAIN (ANALYZE, BUFFERS) <query>;
```

Check:

* sequential scans on large tables
* bad row estimates
* missing indexes
* sort/hash memory pressure
* nested loops on large result sets

---

## Migration Safety

For production databases:

* Avoid long locks
* Avoid rewriting large tables
* Split risky migrations into steps
* Backfill in batches
* Add constraints safely when possible
* Add indexes concurrently when supported

Safer large-table pattern:

```sql
-- 1. Add nullable column
ALTER TABLE users ADD COLUMN timezone text;

-- 2. Backfill in batches outside this migration

-- 3. Add constraint after data is valid
ALTER TABLE users
ADD CONSTRAINT users_timezone_not_blank
CHECK (timezone IS NULL OR length(timezone) > 0);
```

For large indexes:

```sql
CREATE INDEX CONCURRENTLY index_events_on_account_id_created_at
ON events (account_id, created_at DESC);
```

---

## Transactions

Use transactions for multi-step writes:

```sql
BEGIN;

-- related writes

COMMIT;
```

Rollback on failure:

```sql
ROLLBACK;
```

Rules:

* Keep transactions short
* Do not perform slow external work inside transactions
* Lock only what is needed

---

## JSONB Rules

Use `jsonb` only when shape is flexible.

Prefer normal columns when:

* data is queried often
* data needs constraints
* data has stable structure
* joins/reporting are needed

Use GIN only when justified:

```sql
CREATE INDEX index_events_on_metadata
ON events USING gin (metadata);
```

---

## Full-Text Search

Use full-text search when simple `ILIKE` is not enough.

Pattern:

```sql
to_tsvector('english', title || ' ' || body)
@@ plainto_tsquery('english', 'search text')
```

Use GIN indexes for real search workloads.

---

## Data Fix Rules

Before updating/deleting data:

1. Run `SELECT` first
2. Verify affected rows
3. Wrap in transaction
4. Prefer reversible scripts
5. Never run destructive SQL blindly

Example:

```sql
BEGIN;

SELECT count(*) FROM users WHERE status = 'invalid';

UPDATE users
SET status = 'inactive'
WHERE status = 'invalid';

COMMIT;
```

---

## Commands

```bash
psql "$DATABASE_URL"
EXPLAIN (ANALYZE, BUFFERS) <query>;
```

Framework commands may apply:

```bash
rails db:migrate
rails db:rollback
pytest -q
```

---

## Verification Order

```txt
schema check
→ migration dry run
→ targeted query test
→ EXPLAIN ANALYZE
→ app test suite
```

---

## Anti-Patterns

Avoid:

* migrations that lock large tables for too long
* `NOT NULL DEFAULT` on large existing tables without planning
* indexes without query evidence
* missing foreign keys
* business-critical rules only in application code
* JSONB for stable relational data
* performance claims without query plans
* destructive updates without SELECT/transaction

---

## Final Report

```md
## Result
What changed.

## Files changed
- path: purpose

## Verification
- command/query: result

## Notes
Lock risks, rollback plan, follow-ups.
```

---

## Goal

Produce safe, explainable, performant PostgreSQL changes that protect data integrity and work reliably in enterprise systems.