---
language: sql
tags: [sql, query, conditional]
title: Conditional Logic & Null Handling
description: CASE WHEN, COALESCE, NULLIF, FILTER clause, and boolean expressions.
source: pattern
---

```sql
-- CASE WHEN for value mapping
SELECT
    username,
    CASE
        WHEN age < 18 THEN 'minor'
        WHEN age BETWEEN 18 AND 64 THEN 'adult'
        ELSE 'senior'
    END AS age_group,
    CASE role
        WHEN 'admin'   THEN 'Full Access'
        WHEN 'editor'  THEN 'Read/Write'
        WHEN 'viewer'  THEN 'Read Only'
        ELSE 'Unknown'
    END AS access_level
FROM users;

-- CASE inside aggregate for conditional counting
SELECT
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*)                                         AS total,
    COUNT(CASE WHEN status = 'delivered' THEN 1 END) AS delivered,
    COUNT(CASE WHEN status = 'shipped'   THEN 1 END) AS shipped,
    COUNT(CASE WHEN status = 'pending'   THEN 1 END) AS pending
FROM orders
GROUP BY month
ORDER BY month;

-- COALESCE: first non-null value
SELECT
    COALESCE(shipped_at::TEXT, 'not yet shipped') AS shipping_status,
    COALESCE(discount, 0)                         AS effective_discount,
    COALESCE(notes, '(no notes)')                 AS order_notes
FROM orders;

-- NULLIF: avoid division by zero
SELECT
    product_id,
    SUM(quantity)                    AS units_sold,
    COUNT(DISTINCT order_id)         AS order_count,
    ROUND(
        SUM(quantity)::NUMERIC / NULLIF(COUNT(DISTINCT order_id), 0),
        2
    ) AS avg_units_per_order
FROM order_items
GROUP BY product_id;

-- FILTER clause (PostgreSQL): cleaner than CASE in aggregates
SELECT
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*)                                           AS total_orders,
    COUNT(*) FILTER (WHERE status = 'delivered')        AS delivered,
    COUNT(*) FILTER (WHERE status = 'cancelled')        AS cancelled,
    SUM(total) FILTER (WHERE status != 'cancelled')     AS real_revenue
FROM orders
GROUP BY month
ORDER BY month;

-- Boolean expressions
SELECT
    username,
    is_active,
    is_active AND role = 'admin'       AS is_active_admin,
    is_active OR role = 'superuser'    AS can_login,
    NOT is_active                      AS is_disabled
FROM users;

-- Simple if-then with COALESCE + NULLIF combo
SELECT
    username,
    COALESCE(NULLIF(phone, ''), NULLIF(email, ''), 'no contact') AS best_contact
FROM users;

```
