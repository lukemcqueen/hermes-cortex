---
language: sql
tags: [postgres, cte, window-functions, analytics]
title: PostgreSQL CTEs & Window Functions
description: Common Table Expressions (WITH queries) and window functions for analytics.
source: pattern
---

```sql
-- CTE: recursive hierarchy
WITH RECURSIVE org_tree AS (
    SELECT id, name, parent_id, 1 AS depth
    FROM employees
    WHERE manager_id IS NULL
    UNION ALL
    SELECT e.id, e.name, e.manager_id, ot.depth + 1
    FROM employees e
    JOIN org_tree ot ON e.manager_id = ot.id
)
SELECT * FROM org_tree ORDER BY depth, name;

-- CTE: multi-step transformation
WITH user_stats AS (
    SELECT user_id,
           COUNT(*) AS total_orders,
           SUM(total) AS revenue,
           MAX(created_at) AS last_order
    FROM orders
    GROUP BY user_id
),
top_users AS (
    SELECT * FROM user_stats
    ORDER BY revenue DESC
    LIMIT 10
)
SELECT u.email, tu.revenue, tu.total_orders
FROM top_users tu
JOIN users u ON u.id = tu.user_id;

-- Window functions
SELECT
    u.username,
    o.created_at,
    o.total,
    ROW_NUMBER() OVER (PARTITION BY u.id ORDER BY o.created_at DESC) AS order_num,
    SUM(o.total) OVER (PARTITION BY u.id) AS total_spent,
    AVG(o.total) OVER (PARTITION BY u.id ORDER BY o.created_at
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS moving_avg_3,
    LAG(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS prev_order_amount,
    FIRST_VALUE(o.total) OVER (PARTITION BY u.id ORDER BY o.created_at) AS first_order
FROM users u
JOIN orders o ON o.user_id = u.id;
```
