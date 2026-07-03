---
language: sql
tags: [database, connection-pool, pgbouncer, performance]
title: Connection Pooling Patterns
description: PgBouncer config, pool modes, app-side pooling with SQLAlchemy, psycopg2, Prisma, Django
source: pattern
---

# Connection Pooling Patterns

## PgBouncer — pgbouncer.ini

```ini
[databases]
; Map application databases to PostgreSQL backends
mydb = host=127.0.0.1 port=5432 dbname=mydb
analytics = host=10.0.1.50 port=5432 dbname=analytics

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

; === Pool Mode ===
; session      — one connection per application connection (default)
; transaction  — connections returned after each transaction (recommended)
; statement    — connections returned after each statement (aggressive)
pool_mode = transaction

; === Connection Limits ===
; Default pool size per database/user pair
default_pool_size = 25
; Max connections to backend (reserve for superuser/reserved)
max_db_connections = 50
; Reserve pool for emergency use (used when all pool connections are busy)
reserve_pool_size = 5
; Timeout before reserve pool kicks in (seconds)
reserve_pool_timeout = 3.0

; === Queue Settings ===
; Max queued clients waiting for a connection
max_client_conn = 100
; How long a client waits in queue before timeout (seconds)
query_timeout = 30
; How long idle clients stay connected to PgBouncer (seconds)
client_idle_timeout = 600
; How long unused backend connections stay open (seconds)
server_idle_timeout = 300
; Cancel idle in-transaction connections after this time (seconds)
idle_transaction_timeout = 60

; === Tuning ===
; Disable pkt_buf tuning — leave at default unless measured
pkt_buf = 4096
; Listen backlog
listen_backlog = 128
; TCP settings
tcp_keepalive = 1
tcp_keepcnt = 9
tcp_keepidle = 3600
tcp_keepintvl = 75

; === Logging ===
log_connections = 1
log_disconnections = 1
log_pooler_errors = 1
stats_period = 60
; Verbose logging during troubleshooting
verbose = 0

; === Timeouts ===
server_check_delay = 30
server_lifetime = 3600
server_fast_close = 0
```

## Pool Mode Comparison

```sql
-- Use the SHOW POOLS command in pgbouncer to inspect pool state
SHOW POOLS;

-- Output columns:
--   database    — database name
--   user        — user name
--   cl_active   — active client connections
--   cl_waiting  — clients waiting for a connection
--   sv_active   — active server connections
--   sv_idle     — idle server connections
--   sv_used     — server connections being used
--   sv_tested   — server connections being tested
--   maxwait     — longest waiting client (seconds)
--   pool_mode   — current pool mode

-- Check pgbouncer stats
SHOW STATS;

-- Mode decision guide:
--   session:     Legacy apps that hold connections for entire lifecycle
--   transaction: Modern web apps — ideal for most frameworks (Django, Rails)
--   statement:   Only if you have extremely short-lived queries with no transactions

-- Monitor queue wait times — if > 50ms consistently, increase pool size
SELECT database, coalesce(cl_waiting, 0) > 0 AS has_queue,
       maxwait
FROM SHOW POOLS;
```

## Application-Side Pooling

### SQLAlchemy (Python)

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

# Connection pooling configuration
engine = create_engine(
    "postgresql://user:pass@localhost:5432/mydb",
    poolclass=QueuePool,
    pool_size=10,               # Max connections in pool
    max_overflow=5,             # Extra connections beyond pool_size
    pool_timeout=10,            # Seconds to wait for a connection from pool
    pool_pre_ping=True,         # Verify connection before use
    pool_recycle=3600,          # Recycle connections after 1 hour
)

# Or for async (SQLAlchemy 1.4+ with psycopg2 or asyncpg):
# from sqlalchemy.ext.asyncio import create_async_engine
# engine = create_async_engine(
#     "postgresql+asyncpg://user:pass@localhost:5432/mydb",
#     pool_size=10,
#     max_overflow=5,
# )
```

### psycopg2 (Python — minimal)

```python
import psycopg2
from psycopg2 import pool

# ThreadedConnectionPool for multi-threaded apps
conn_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=10,
    host="localhost",
    port=6432,          # Point at PgBouncer, not directly at PostgreSQL
    dbname="mydb",
    user="app_user",
    password="secret",
)

# Usage
conn = conn_pool.getconn()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
finally:
    conn_pool.putconn(conn)

# Close all connections on shutdown
conn_pool.closeall()
```

### Prisma (TypeScript/Node.js)

```typescript
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient({
  datasources: {
    db: {
      url: "postgresql://user:pass@localhost:6432/mydb?connection_limit=10",
    },
  },
  // Connection pool config via Prisma
  // connection_limit is set in the connection string
});

// Prisma manages internal connection pooling
// Recommended to point at PgBouncer in transaction mode

// For serverless (Lambda, etc.), use Prisma Data Proxy or
// set PgBouncer pool_mode = transaction
```

### Django (Python)

```python
# settings.py — using PgBouncer as intermediary is recommended
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "localhost",
        "PORT": 6432,          # PgBouncer port
        "NAME": "mydb",
        "USER": "app_user",
        "PASSWORD": "secret",
        "CONN_MAX_AGE": 0,     # PgBouncer handles persistence
        "OPTIONS": {
            "pool": True,       # Django 5.1+ persistent connections
        },
    }
}

# For high-concurrency setups, use django-db-geventpool or
# set CONN_MAX_AGE to None and let PgBouncer manage pooling
```

## PgBouncer Auth File

```bash
# /etc/pgbouncer/userlist.txt
# Format: "username" "password"  (for scram-sha-256 or md5)

# Create entries using the pgbouncer auth helper
# PgBouncer 1.18+ can use SCRAM
echo '"app_user"' '"my_secure_password"' >> /etc/pgbouncer/userlist.txt
echo '"admin_user"' '"admin_password"' >> /etc/pgbouncer/userlist.txt
echo '"readonly_user"' '"readonly_pass"' >> /etc/pgbouncer/userlist.txt
```

## Pool Sizing Formulas

```sql
-- Connection count formulas:
--   Active Connections = (max_connections * pool_overflow_factor)
--   PgBouncer pool = (CPU_cores * 2) + effective_spindle_count
--   Typical OLTP: 10-50 per PgBouncer pool

-- Monitor connection saturation
SELECT
    database,
    cl_active,
    cl_waiting,
    sv_active,
    sv_idle,
    maxwait,
    CASE WHEN cl_waiting > 0 THEN 'BACKPRESSURE' ELSE 'OK' END AS status
FROM SHOW POOLS;

-- Ideal state: cl_waiting = 0, sv_idle > 0 (headroom)
-- Warning:    cl_waiting > 0 consistently — increase pool size
-- Danger:     maxwait > 5 seconds — increase pool or optimize queries
```