---
language: sql
tags: [sql, dml, crud]
title: Basic CRUD Operations
description: INSERT, SELECT, UPDATE, and DELETE with WHERE, ORDER BY, LIMIT, and RETURNING clauses.
source: pattern
---

```sql
-- INSERT: Create a new user
INSERT INTO users (username, email, full_name, age, role)
VALUES ('jdoe', 'jdoe@example.com', 'Jane Doe', 32, 'editor')
RETURNING *;

-- INSERT multiple rows
INSERT INTO products (name, sku, price, stock)
VALUES
    ('Widget Alpha', 'WGT-001', 19.99, 100),
    ('Widget Beta',  'WGT-002', 29.99, 200),
    ('Widget Gamma', 'WGT-003', 39.99, 150)
RETURNING id, name, sku;

-- SELECT with filtering, ordering, and limiting
SELECT id, username, email, role, created_at
FROM users
WHERE is_active = TRUE
  AND role IN ('editor', 'admin')
ORDER BY created_at DESC
LIMIT 20;

-- UPDATE with WHERE and RETURNING
UPDATE orders
SET status = 'shipped',
    shipped_at = NOW()
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '2 days'
RETURNING id, user_id, status, shipped_at;

-- DELETE with subquery condition
DELETE FROM order_items
WHERE order_id IN (
    SELECT id FROM orders WHERE status = 'cancelled'
)
RETURNING *;

-- Full SELECT with offset for pagination
SELECT o.id, o.total, u.username, o.created_at
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'pending'
ORDER BY o.created_at ASC
LIMIT 25 OFFSET 0;

```
