---
language: sql
tags: [sql, query, window-functions]
title: Window Functions
description: ROW_NUMBER, RANK, DENSE_RANK, LAG/LEAD, SUM OVER PARTITION BY, and NTILE.
source: pattern
---

```sql
-- ROW_NUMBER: rank orders per user by date
SELECT
    u.username,
    o.id AS order_id,
    o.total,
    o.created_at,
    ROW_NUMBER() OVER (PARTITION BY u.id ORDER BY o.created_at DESC) AS order_num
FROM users u
JOIN orders o ON u.id = o.user_id;

-- RANK and DENSE_RANK: product sales ranking
SELECT
    p.name,
    SUM(oi.quantity) AS units_sold,
    RANK()       OVER (ORDER BY SUM(oi.quantity) DESC) AS rank,
    DENSE_RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS dense_rank
FROM products p
JOIN order_items oi ON p.id = oi.product_id
GROUP BY p.id, p.name;

-- LAG and LEAD: compare current order to previous
SELECT
    u.username,
    o.id,
    o.total,
    o.created_at,
    LAG(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS prev_order_total,
    LEAD(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS next_order_total,
    o.total - LAG(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS diff_from_prev
FROM users u
JOIN orders o ON u.id = o.user_id;

-- Moving sum over partition
SELECT
    o.user_id,
    o.created_at::DATE AS order_date,
    o.total,
    SUM(o.total) OVER (
        PARTITION BY o.user_id
        ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM orders o
ORDER BY o.user_id, o.created_at;

-- NTILE: divide users into deciles by spend
SELECT
    u.username,
    SUM(o.total) AS total_spent,
    NTILE(4) OVER (ORDER BY SUM(o.total) DESC) AS quartile
FROM users u
JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username
ORDER BY total_spent DESC;

-- First and last values in a window
SELECT DISTINCT
    u.username,
    FIRST_VALUE(o.id) OVER (
        PARTITION BY u.id ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_order_id,
    LAST_VALUE(o.id) OVER (
        PARTITION BY u.id ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_id
FROM users u
JOIN orders o ON u.id = o.user_id;

```
