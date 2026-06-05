---
language: sql
tags: [sql, dml, transactions, concurrency]
title: Transactions & Concurrency Control
description: BEGIN, COMMIT, ROLLBACK, SAVEPOINT, isolation levels, and explicit locking.
source: pattern
---

```sql
-- Basic transaction with COMMIT
BEGIN;
UPDATE accounts SET balance = balance - 100.00 WHERE id = 1;
UPDATE accounts SET balance = balance + 100.00 WHERE id = 2;
COMMIT;

-- Transaction with ROLLBACK on error
BEGIN;
DELETE FROM orders WHERE id = 9999;
-- Oops, wrong order — undo it
ROLLBACK;

-- SAVEPOINT for partial rollback
BEGIN;
INSERT INTO orders (user_id, total) VALUES (1, 250.00);
SAVEPOINT order_created;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (LASTVAL(), 42, 2, 125.00);

-- Something went wrong with items, rollback just that part
ROLLBACK TO SAVEPOINT order_created;
-- Order still exists, fix the items
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (LASTVAL(), 42, 1, 250.00);
COMMIT;

-- Explicit isolation level
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
UPDATE inventory SET stock = stock - 5 WHERE product_id = 10 AND stock >= 5;
COMMIT;

-- Row-level locking (prevent concurrent updates)
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- Now safely update knowing no one else changed it
UPDATE accounts SET balance = balance - 50 WHERE id = 1;
COMMIT;

-- Advisory lock for application-level concurrency
BEGIN;
SELECT pg_advisory_xact_lock(12345);
-- Critical section — only one session at a time
UPDATE counters SET value = value + 1 WHERE name = 'api_calls';
COMMIT;

```
