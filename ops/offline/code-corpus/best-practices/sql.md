---
language: sql
tags: [sql, best-practices, database, design]
title: SQL Best Practices
description: Normalization to 3NF, naming conventions (snake_case), indexes on FK/WHERE columns, avoid SELECT *, CTEs over subqueries, EXPLAIN before deploying
source: pattern
---

# SQL Best Practices

## Normalization (3NF)
Structure tables to reduce redundancy:

```sql
-- 1NF: Atomic columns, no repeating groups
-- 2NF: Every non-key column fully dependent on the whole PK
-- 3NF: No transitive dependencies (non-key depends on another non-key)

-- Example: Normalized schema
CREATE TABLE authors (
    author_id SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    email     TEXT UNIQUE NOT NULL
);

CREATE TABLE books (
    book_id   SERIAL PRIMARY KEY,
    title     TEXT NOT NULL,
    isbn      TEXT UNIQUE NOT NULL,
    author_id INTEGER NOT NULL REFERENCES authors(author_id)
);

-- NOT this: denormalized with redundant author info per book
```

## Naming Conventions (snake_case)
Be consistent and descriptive:

```sql
-- Tables: plural, snake_case
CREATE TABLE order_items ( … );

-- Columns: singular, snake_case
CREATE TABLE users (
    user_id        SERIAL PRIMARY KEY,
    full_name      TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active      BOOLEAN NOT NULL DEFAULT true
);

-- Indexes: idx_table_column(s)
CREATE INDEX idx_orders_user_id ON orders(user_id);
```

## Indexes on FK and WHERE Columns
Index foreign keys and frequently filtered columns:

```sql
CREATE TABLE reviews (
    review_id  SERIAL PRIMARY KEY,
    book_id    INTEGER NOT NULL REFERENCES books(book_id),
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    rating     SMALLINT CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reviews_book_id  ON reviews(book_id);   -- FK
CREATE INDEX idx_reviews_user_id  ON reviews(user_id);   -- FK
CREATE INDEX idx_reviews_rating   ON reviews(rating);    -- WHERE filter
CREATE INDEX idx_reviews_created  ON reviews(created_at); -- ORDER / range
```

## Avoid `SELECT *`
Always enumerate columns — it's self-documenting and resilient to schema changes:

```sql
-- Bad
SELECT * FROM users WHERE is_active = true;

-- Good
SELECT user_id, full_name, email
FROM users
WHERE is_active = true;
```

## CTEs Over Subqueries
Use Common Table Expressions (WITH clauses) for readability:

```sql
WITH active_users AS (
    SELECT user_id, full_name, email
    FROM users
    WHERE is_active = true
),
recent_orders AS (
    SELECT user_id, COUNT(*) AS order_count
    FROM orders
    WHERE ordered_at >= now() - INTERVAL '90 days'
    GROUP BY user_id
)
SELECT au.full_name, au.email, COALESCE(ro.order_count, 0) AS recent_orders
FROM active_users au
LEFT JOIN recent_orders ro ON au.user_id = ro.user_id
ORDER BY ro.order_count DESC NULLS LAST;
```

## EXPLAIN Before Deploying
Analyze query plans on production-like data:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT o.order_id, o.total, u.full_name
FROM orders o
JOIN users u ON u.user_id = o.user_id
WHERE o.ordered_at >= '2026-01-01'
ORDER BY o.total DESC
LIMIT 100;
```

## Additional Patterns
- Use `TIMESTAMPTZ` (TIMESTAMP WITH TIME ZONE) over bare `TIMESTAMP`
- Use `CHECK` constraints for column-level validation
- Prefer `NOT NULL` unless you have a compelling reason for NULL
- Use `ON DELETE CASCADE` / `ON DELETE SET NULL` judiciously
- Use `COALESCE` for default values in queries
- Test migrations in a transaction (`BEGIN … ROLLBACK`)