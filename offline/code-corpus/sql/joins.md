---
language: sql
tags: [sql, query, joins]
title: JOIN Operations
description: INNER, LEFT, RIGHT, and FULL OUTER JOINs with multiple tables.
source: pattern
---

```sql
-- INNER JOIN: only matching rows
SELECT o.id AS order_id, o.total, c.name AS customer, c.email
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id;

-- LEFT JOIN: all customers, orders where they exist
SELECT c.name, c.email, o.id AS order_id, o.total
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id;

-- RIGHT JOIN: all orders, customer info where it exists
SELECT o.id AS order_id, o.total, c.name
FROM customers c
RIGHT JOIN orders o ON c.id = o.customer_id;

-- FULL OUTER JOIN: everything from both sides
SELECT e.name AS employee, d.name AS department
FROM employees e
FULL OUTER JOIN departments d ON e.dept_id = d.id;

-- Multiple joins across three tables
SELECT u.username, o.id AS order_id, p.name AS product, oi.quantity
FROM users u
INNER JOIN orders o ON u.id = o.user_id
INNER JOIN order_items oi ON o.id = oi.order_id
INNER JOIN products p ON oi.product_id = p.id
WHERE o.status = 'delivered'
ORDER BY o.created_at DESC;

-- Self-join: employees and their managers
SELECT e.name AS employee, m.name AS manager
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.id;

```
