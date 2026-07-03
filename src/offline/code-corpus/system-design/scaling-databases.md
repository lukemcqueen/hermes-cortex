---
title: Scaling Databases
description: Database scaling strategies including read replicas, connection pooling with PgBouncer, sharding (hash/range/geo), partitioning vs sharding, vertical vs horizontal scaling, and migration strategies.
language: sql
tags: [system-design, scaling, database, sharding]
---

# Scaling Databases

## Overview

As your application grows, a single database instance becomes a bottleneck. This snippet covers strategies to scale databases: vertical vs horizontal scaling, read replicas, connection pooling, sharding, partitioning, and safe migration techniques.

---

## Vertical vs Horizontal Scaling

| Axis | Vertical (Scale Up) | Horizontal (Scale Out) |
|------|-------------------|----------------------|
| **What** | Bigger server (more CPU/RAM/IOPS) | More servers (distributed) |
| **Limit** | Hardware ceiling | Theoretically unlimited |
| **Complexity** | Low — just upgrade the instance | High — sharding, replication, consistency |
| **Downtime** | Usually required | Can be zero-downtime |
| **When** | Early stage, < ~100 GB data | Large scale, > ~1 TB data |

**Rule of thumb:** Scale vertically until it's too expensive or you hit hardware limits, then scale horizontally.

---

## Read Replicas

Offload read queries to replica nodes. Writes go to the primary; reads can go to any replica.

### Setting Up Replicas (PostgreSQL)

```sql
-- On the primary, configure replication
-- postgresql.conf on primary
wal_level = replica
max_wal_senders = 5
wal_keep_size = 1024  -- MB

-- On the replica, configure streaming replication
-- postgresql.conf on replica
primary_conninfo = 'host=primary-db.example.com port=5432 user=replicator password=secret'
hot_standby = on
```

### Routing Reads to Replicas (Application Level)

```python
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager

# Two connection pools: one for writes, one for reads
write_pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn="dbname=app primary_host=...")
read_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn="dbname=app replica_host=...")

@contextmanager
def get_write_conn():
    conn = write_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        write_pool.putconn(conn)

@contextmanager
def get_read_conn():
    conn = read_pool.getconn()
    try:
        yield conn
    finally:
        read_pool.putconn(conn)

# Then in your code:
def create_order(user_id: int, amount: float):
    with get_write_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (user_id, amount) VALUES (%s, %s)",
                (user_id, amount)
            )

def list_orders(user_id: int):
    with get_read_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            return cur.fetchall()
```

**Replication Lag:** Replicas may be seconds behind the primary. Use `synchronous_commit = on` for critical reads, or route reads for the same user to the primary until replication catches up.

---

## Connection Pooling with PgBouncer

PgBouncer sits between your application and PostgreSQL, multiplexing many client connections into a smaller pool of database connections.

```ini
; pgbouncer.ini
[databases]
app = host=127.0.0.1 port=5432 dbname=app

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

; Pooling modes:
; session — connection held for entire session (default)
; transaction — reuses connections between transactions (recommended)
; statement — reuses between statements (rare)
pool_mode = transaction

; Connection limits
default_pool_size = 25
max_client_conn = 200
max_db_connections = 50

; Timeouts
server_idle_timeout = 600
client_idle_timeout = 0
```

### Application Connection String

```
# Instead of: postgresql://user:pass@localhost:5432/app
# Point to PgBouncer:
postgresql://user:pass@localhost:6432/app
```

```python
import psycopg2
import psycopg2.pool

# Even with PgBouncer, use connection pooling in your app
pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=10,
    dsn="postgresql://app_user:secret@localhost:6432/app"
)
```

---

## Sharding Strategies

Sharding splits data across multiple database instances (shards) based on a shard key.

### Hash-Based Sharding

```python
import hashlib

NUM_SHARDS = 8

def get_shard(user_id: str) -> int:
    """Deterministically map a user_id to a shard."""
    hash_val = int(hashlib.sha256(user_id.encode()).hexdigest(), 16)
    return hash_val % NUM_SHARDS
```

```sql
-- Each shard has its own database instance with the same schema
-- Shard 0: db_shard_0
-- Shard 1: db_shard_1
-- ...

-- Query must include shard key to know which shard to hit
SELECT * FROM orders WHERE user_id = 'abc123';
-- Application computes shard, then connects to that shard
```

**Pros:** Even distribution; predictable.
**Cons:** Adding shards requires rehashing (use consistent hashing to mitigate).

### Range-Based Sharding

```sql
-- users_0_1000000: users with id 1 - 1,000,000
-- users_1000001_2000000: users with id 1,000,001 - 2,000,000

-- Each shard holds a contiguous range of the shard key
-- Application routes based on the range table:

CREATE TABLE shard_ranges (
    shard_id   INT PRIMARY KEY,
    min_key    BIGINT NOT NULL,
    max_key    BIGINT NOT NULL,
    host       TEXT NOT NULL
);

INSERT INTO shard_ranges VALUES
    (0, 1, 1000000, 'db-shard-0.example.com'),
    (1, 1000001, 2000000, 'db-shard-1.example.com');
```

**Pros:** Range queries efficient; easy to add new ranges.
**Cons:** Hot spots on recent ranges (e.g., newest users); uneven distribution.

### Geographic Sharding

```python
GEO_SHARD_MAP = {
    "us_east": "db-us-east.example.com",
    "us_west": "db-us-west.example.com",
    "eu_west": "db-eu-west.example.com",
    "ap_southeast": "db-ap-southeast.example.com",
}

def get_shard_for_region(region: str) -> str:
    return GEO_SHARD_MAP.get(region, "db-us-east.example.com")
```

**Pros:** Data lives close to users; compliance with data sovereignty laws.
**Cons:** Cross-region queries are expensive; uneven load distribution.

---

## Partitioning vs Sharding

| Feature | Partitioning | Sharding |
|---------|-------------|----------|
| **Scope** | Within a single database instance | Across multiple database instances |
| **Transparency** | Transparent to the application | Application or proxy must route |
| **Management** | Built into PostgreSQL (`PARTITION BY`) | Custom application logic or middleware (Vitess, Citus) |
| **Query Span** | All partitions visible in one query | Cross-shard queries require scatter-gather |

### PostgreSQL Partitioning (Range)

```sql
-- Create partitioned table
CREATE TABLE events (
    id          BIGSERIAL,
    created_at  TIMESTAMP NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE events_2025_01 PARTITION OF events
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE events_2025_02 PARTITION OF events
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

CREATE TABLE events_2025_03 PARTITION OF events
    FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');

-- Queries against 'events' automatically hit the right partition
EXPLAIN SELECT * FROM events WHERE created_at >= '2025-02-15';
-- Note: Seq Scan on events_2025_02 ...
```

---

## Migration Strategies

### Zero-Downtime Schema Migration

```sql
-- Step 1: Add new column (non-blocking with DEFAULT NULL)
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT NULL;

-- Step 2: Backfill in batches (use a background job, not a single UPDATE)
-- Batch 1: users 1-10000
UPDATE users SET email_verified = FALSE
WHERE id BETWEEN 1 AND 10000 AND email_verified IS NULL;

-- Batch 2: users 10001-20000
UPDATE users SET email_verified = FALSE
WHERE id BETWEEN 10001 AND 20000 AND email_verified IS NULL;

-- Step 3: Set NOT NULL after all rows populated
ALTER TABLE users ALTER COLUMN email_verified SET NOT NULL;
ALTER TABLE users ALTER COLUMN email_verified SET DEFAULT FALSE;
```

### Expanding Hash Shards (Consistent Hashing)

```python
import hashlib

class ConsistentHash:
    def __init__(self, nodes: list[str], replicas: int = 100):
        self.replicas = replicas
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []

        for node in nodes:
            self.add_node(node)

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str) -> None:
        for i in range(self.replicas):
            h = self._hash(f"{node}:{i}")
            self.ring[h] = node
            self.sorted_keys.append(h)
        self.sorted_keys.sort()

    def get_node(self, key: str) -> str:
        if not self.ring:
            return ""
        h = self._hash(key)
        # Find the first node with hash >= key hash (binary search)
        import bisect
        idx = bisect.bisect_left(self.sorted_keys, h)
        if idx == len(self.sorted_keys):
            idx = 0
        return self.ring[self.sorted_keys[idx]]

# Usage
nodes = ["shard-0", "shard-1", "shard-2", "shard-3"]
ch = ConsistentHash(nodes)

user_shard = ch.get_node("user_abc123")  # -> "shard-2"

# Adding a new shard only relocates ~1/N of keys
ch.add_node("shard-4")  # Now 5 shards; only ~20% of keys move
```

---

## Key Takeaways

- **Read replicas** are the easiest first step for read-heavy workloads.
- **PgBouncer** prevents connection exhaustion without application changes.
- **Sharding** by hash gives the most even distribution; **range** sharding is better for sequential data; **geo** sharding is best for latency compliance.
- **Partitioning** cleans up large tables inside one DB; **sharding** distributes across DBs.
- **Vertical scaling** is simpler but finite; **horizontal scaling** is complex but necessary at scale.
- Always plan migrations (backfill, expand shards) with zero-downtime patterns.
