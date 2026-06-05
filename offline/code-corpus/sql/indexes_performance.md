---
language: sql
tags: [sql, ddl, performance, indexes]
title: Indexes & Performance Tuning
description: CREATE INDEX, composite indexes, partial indexes, EXPLAIN ANALYZE, and covering indexes.
source: pattern
---

```sql
-- Single-column B-tree index
CREATE INDEX idx_users_email ON users(email);

-- Composite index (column order matters: most selective first)
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- Partial index: only active users
CREATE INDEX idx_users_active ON users(username) WHERE is_active = TRUE;

-- Unique partial index: enforce one active admin per email
CREATE UNIQUE INDEX idx_unique_active_admin
ON users(email) WHERE role = 'admin' AND is_active = TRUE;

-- Covering index (INCLUDE columns to avoid table lookups)
CREATE INDEX idx_orders_list ON orders(user_id, created_at DESC)
INCLUDE (total, status);

-- Index on expression
CREATE INDEX idx_users_lower_email ON users(LOWER(email));

-- Using EXPLAIN ANALYZE to check query plan
EXPLAIN ANALYZE
SELECT u.username, o.total, o.created_at
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.email = 'jdoe@example.com'
ORDER BY o.created_at DESC
LIMIT 10;

-- Understanding the plan output
-- Seq Scan on users  (cost=0.00..12.32 rows=1 width=...)
--   Filter: (email = 'jdoe@example.com'::text)
--   ->  Index Scan using idx_orders_user_created on orders  (cost=...)
--         Index Cond: (user_id = users.id)

-- Drop indexes when no longer needed
DROP INDEX IF EXISTS idx_old_unused_index;

```
