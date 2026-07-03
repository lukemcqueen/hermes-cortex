---
language: sql
tags: [postgres, queries, indexing, performance]
title: PostgreSQL Queries & Indexing
description: SELECT with JOINs, WHERE, GROUP BY, ORDER BY, and index strategies with EXPLAIN ANALYZE.
source: pattern
---

```sql
-- Basic SELECT with JOINs
SELECT u.email, p.title, p.created_at
FROM users u
JOIN posts p ON p.user_id = u.id
WHERE u.is_active = true
  AND p.published = true
ORDER BY p.created_at DESC
LIMIT 20;

-- Aggregation with GROUP BY
SELECT u.role,
       COUNT(*) AS total_users,
       COUNT(p.id) AS total_posts,
       AVG(LENGTH(p.body))::int AS avg_post_length
FROM users u
LEFT JOIN posts p ON p.user_id = u.id
GROUP BY u.role
HAVING COUNT(*) > 5
ORDER BY total_users DESC;

-- Index types
CREATE INDEX idx_users_email ON users(email);                         -- B-tree (default)
CREATE UNIQUE INDEX idx_users_handle ON users(handle);                -- unique constraint
CREATE INDEX idx_users_roles ON users USING GIN (roles);              -- GIN for arrays/jsonb
CREATE INDEX idx_posts_created ON posts(created_at DESC);             -- descending order
CREATE INDEX idx_posts_tsv ON posts USING GIN (to_tsvector('english', title || ' ' || body)); -- full-text

-- Partial / covering index
CREATE INDEX idx_users_active_email ON users(email)
    INCLUDE (username, role)
    WHERE is_active = true;

-- Analyze query performance
EXPLAIN ANALYZE
SELECT u.email, COUNT(p.id) AS post_count
FROM users u
LEFT JOIN posts p ON p.user_id = u.id
WHERE u.created_at > now() - interval '30 days'
GROUP BY u.id, u.email;
```
