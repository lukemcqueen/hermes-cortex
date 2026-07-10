---
language: sql
tags: [sql, ddl, schema, alter]
title: Table Constraints & ALTER TABLE Operations
description: ALTER TABLE ADD/DROP COLUMN, ADD/DROP CONSTRAINT, modify types, and RENAME.
source: pattern
---

```sql
-- Add a new column
ALTER TABLE users
ADD COLUMN phone VARCHAR(20);

-- Add column with default value (non-nullable after backfill)
ALTER TABLE users
ADD COLUMN timezone VARCHAR(50) NOT NULL DEFAULT 'UTC';

-- Drop a column
ALTER TABLE users
DROP COLUMN IF EXISTS obsolete_field;

-- Add a check constraint
ALTER TABLE orders
ADD CONSTRAINT chk_positive_total CHECK (total >= 0);

-- Add a foreign key constraint
ALTER TABLE order_items
ADD CONSTRAINT fk_oi_product
    FOREIGN KEY (product_id) REFERENCES products(id)
    ON DELETE RESTRICT;

-- Add a unique constraint
ALTER TABLE users
ADD CONSTRAINT uq_users_phone UNIQUE (phone);

-- Drop a constraint
ALTER TABLE orders
DROP CONSTRAINT IF EXISTS chk_positive_total;

-- Modify column data type
ALTER TABLE products
ALTER COLUMN price TYPE NUMERIC(12,2);

-- Set / drop column default
ALTER TABLE orders
ALTER COLUMN status SET DEFAULT 'pending';

ALTER TABLE orders
ALTER COLUMN status DROP DEFAULT;

-- Set NOT NULL / drop NOT NULL
ALTER TABLE users
ALTER COLUMN phone SET NOT NULL;

ALTER TABLE users
ALTER COLUMN phone DROP NOT NULL;

-- Rename a column
ALTER TABLE users
RENAME COLUMN full_name TO display_name;

-- Rename the table itself
ALTER TABLE old_table_name RENAME TO new_table_name;

-- Add a primary key (composite)
ALTER TABLE order_items
ADD PRIMARY KEY (order_id, product_id);

-- Enable/disable a trigger
ALTER TABLE orders DISABLE TRIGGER trg_orders_updated_at;
ALTER TABLE orders ENABLE TRIGGER trg_orders_updated_at;

```
