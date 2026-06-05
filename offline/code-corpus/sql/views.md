---
language: sql
tags: [sql, ddl, views]
title: Views & Materialized Views
description: CREATE VIEW, CREATE MATERIALIZED VIEW, WITH CHECK OPTION, and refreshing.
source: pattern
---

```sql
-- Simple view: active users only
CREATE VIEW active_users AS
SELECT id, username, email, full_name, role, created_at
FROM users
WHERE is_active = TRUE;

-- View with CHECK OPTION: prevents inserts/updates that would make rows invisible
CREATE VIEW high_value_orders AS
SELECT id, user_id, total, status, created_at
FROM orders
WHERE total >= 500
WITH CHECK OPTION;

-- Attempting INSERT below threshold fails:
-- INSERT INTO high_value_orders (user_id, total, status)
-- VALUES (1, 100, 'pending');  -- ERROR: new row violates WITH CHECK OPTION

-- View joining multiple tables
CREATE VIEW customer_order_summary AS
SELECT
    u.id AS user_id,
    u.username,
    u.email,
    COUNT(o.id) AS order_count,
    SUM(o.total) AS lifetime_value,
    MAX(o.created_at) AS last_order_date
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username, u.email;

-- Materialized view for expensive aggregations
CREATE MATERIALIZED VIEW mv_monthly_sales AS
SELECT
    EXTRACT(YEAR FROM o.created_at)  AS year,
    EXTRACT(MONTH FROM o.created_at) AS month,
    p.category,
    COUNT(DISTINCT o.id)              AS order_count,
    SUM(oi.quantity)                  AS units_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
GROUP BY year, month, p.category
WITH DATA;

-- Refresh materialized view (blocking)
REFRESH MATERIALIZED VIEW mv_monthly_sales;

-- Non-blocking refresh (PostgreSQL 9.4+)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_sales;

-- Drop a view
DROP VIEW IF EXISTS old_unused_view CASCADE;

```
