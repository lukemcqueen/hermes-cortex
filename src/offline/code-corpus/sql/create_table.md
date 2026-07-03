---
language: sql
tags: [sql, ddl, constraints]
title: CREATE TABLE with Constraints
description: Table creation with PRIMARY KEY, FOREIGN KEY, UNIQUE, NOT NULL, DEFAULT, CHECK, and indexes.
source: pattern
---

```sql
-- Users table with all common constraints
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    full_name       VARCHAR(100) NOT NULL,
    age             INTEGER CHECK (age >= 0 AND age <= 150),
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orders table with foreign key constraint
CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')),
    total           NUMERIC(10,2) NOT NULL CHECK (total >= 0),
    shipped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- Order items join table with composite primary key
CREATE TABLE order_items (
    order_id        INTEGER NOT NULL,
    product_id      INTEGER NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL,

    PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_oi_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_oi_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE RESTRICT
);

-- Indexes for performance
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
CREATE UNIQUE INDEX idx_active_user_roles ON users(username) WHERE is_active = TRUE;

```
