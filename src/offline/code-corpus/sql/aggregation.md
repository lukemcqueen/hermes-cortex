---
language: sql
tags: [sql, query, aggregation, group-by]
title: Aggregation & GROUP BY
description: COUNT, SUM, AVG, MIN, MAX with GROUP BY, HAVING, and GROUPING SETS.
source: pattern
---

```sql
-- Basic aggregate functions
SELECT
    COUNT(*)                    AS total_orders,
    COUNT(DISTINCT user_id)     AS unique_customers,
    SUM(total)                  AS revenue,
    AVG(total)                  AS avg_order_value,
    MIN(total)                  AS smallest_order,
    MAX(total)                  AS largest_order
FROM orders
WHERE created_at >= '2024-01-01';

-- GROUP BY with HAVING filter
SELECT
    u.role,
    COUNT(u.id)                    AS user_count,
    ROUND(AVG(o.total), 2)         AS avg_spend
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.role
HAVING COUNT(o.id) > 5
ORDER BY avg_spend DESC;

-- GROUP BY multiple columns
SELECT
    EXTRACT(YEAR FROM o.created_at)  AS year,
    EXTRACT(MONTH FROM o.created_at) AS month,
    o.status,
    COUNT(*)                         AS order_count,
    SUM(o.total)                     AS monthly_revenue
FROM orders o
GROUP BY year, month, o.status
ORDER BY year DESC, month DESC, o.status;

-- GROUPING SETS: subtotals and grand totals
SELECT
    COALESCE(p.category, 'ALL')       AS category,
    COALESCE(p.name, 'ALL')           AS product,
    SUM(oi.quantity)                  AS units_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.id
GROUP BY GROUPING SETS (
    (p.category, p.name),
    (p.category),
    ()
)
ORDER BY category, product;

```
