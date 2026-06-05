---
language: sql
tags: [sql, query, subqueries, cte]
title: Subqueries & Common Table Expressions
description: Scalar subqueries, correlated subqueries, WITH/CTE, and recursive CTEs.
source: pattern
---

```sql
-- Scalar subquery in SELECT
SELECT
    o.id,
    o.total,
    (SELECT AVG(total) FROM orders) AS overall_avg,
    o.total - (SELECT AVG(total) FROM orders) AS difference_from_avg
FROM orders o;

-- Subquery in WHERE clause
SELECT u.username, u.email
FROM users u
WHERE u.id IN (
    SELECT user_id FROM orders
    WHERE total > 1000 AND status = 'delivered'
);

-- Correlated subquery: each user's latest order
SELECT u.username, u.email, o.id AS order_id, o.total, o.created_at
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.created_at = (
    SELECT MAX(o2.created_at)
    FROM orders o2
    WHERE o2.user_id = u.id
);

-- Simple CTE
WITH user_revenue AS (
    SELECT
        u.id,
        u.username,
        COUNT(o.id) AS order_count,
        SUM(o.total) AS total_spent
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    GROUP BY u.id, u.username
)
SELECT * FROM user_revenue
WHERE total_spent > 500
ORDER BY total_spent DESC;

-- Recursive CTE: organizational hierarchy
WITH RECURSIVE org_tree AS (
    -- Base case: top-level employees
    SELECT id, name, manager_id, 1 AS level
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: direct reports
    SELECT e.id, e.name, e.manager_id, t.level + 1
    FROM employees e
    JOIN org_tree t ON e.manager_id = t.id
)
SELECT * FROM org_tree
ORDER BY level, name;

-- CTE chain (multiple CTEs)
WITH
    active_users AS (
        SELECT id, username, email FROM users WHERE is_active = TRUE
    ),
    user_orders AS (
        SELECT u.id, u.username, COUNT(o.id) AS cnt
        FROM active_users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id, u.username
    )
SELECT * FROM user_orders WHERE cnt = 0;

```
