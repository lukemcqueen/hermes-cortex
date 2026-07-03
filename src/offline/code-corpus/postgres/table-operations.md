---
language: sql
tags: [postgres, ddl, tables, schema]
title: PostgreSQL Table Operations
description: CREATE TABLE, ALTER, DROP, TRUNCATE with constraints, defaults, and data types.
source: pattern
---

```sql
-- Create table with constraints
CREATE TABLE users (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    username    TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'admin', 'moderator')),
    is_active   BOOLEAN NOT NULL DEFAULT true,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Foreign key + composite index
CREATE TABLE posts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT,
    published   BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_posts_user_published ON posts(user_id, published)
    WHERE published = true;

-- Alter table
ALTER TABLE users ADD COLUMN avatar_url TEXT;
ALTER TABLE users ALTER COLUMN username SET NOT NULL;
ALTER TABLE users DROP COLUMN IF EXISTS obsolete_field;
ALTER TABLE users RENAME COLUMN username TO handle;
ALTER TABLE users RENAME TO accounts;

-- Drop / truncate
TRUNCATE TABLE temp_data;
TRUNCATE TABLE logs RESTART IDENTITY CASCADE;
DROP TABLE IF EXISTS deprecated_table;
```
