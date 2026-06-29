---
language: sql
tags: [errors, debugging, database, postgres]
title: Common Database Errors
description: Frequent DB errors — connection refused, migration conflicts, deadlocks, duplicate key, too many connections, SSL/TLS handshake — with messages, causes, and fixes
source: pattern
---

```sql
-- ---------------------------------------------------------------------------
-- 1. Connection refused
-- ---------------------------------------------------------------------------
-- Error message:
--   could not connect to server: Connection refused
--     Is the server running on host "localhost" (::1) and accepting
--     TCP/IP connections on port 5432?
--   FATAL: no pg_hba.conf entry for host "192.168.1.100"
--   Can't connect to MySQL server on 'db.example.com' (61)
--
-- Cause:
--   - Database server not running
--   - Wrong hostname / port in connection string
--   - Firewall blocking the port
--   - pg_hba.conf not configured to allow the connection
--   - PostgreSQL only listening on localhost, not on network interface
--
-- Fixes:

-- Fix 1: Check if the server is running
-- psql:
\! pg_isready
SELECT * FROM pg_stat_activity WHERE datname = 'mydb';

-- Shell:
-- pg_isready -h localhost -p 5432
-- sudo systemctl status postgresql
-- sudo systemctl start postgresql

-- Fix 2: Check PostgreSQL is listening on the right interface
-- In postgresql.conf:
-- listen_addresses = '*'          # Listen on all interfaces
-- listen_addresses = 'localhost,192.168.1.50'  # Specific interfaces
-- Then restart: sudo systemctl restart postgresql

-- Fix 3: Update pg_hba.conf to allow connections
-- Add to pg_hba.conf:
-- host    all    all    192.168.1.0/24    md5
-- Then reload: SELECT pg_reload_conf();

-- Fix 4: Check firewall (Linux/macOS)
-- sudo ufw status
-- sudo ufw allow 5432/tcp

-- Fix 5: Test connectivity with a simple tool
-- telnet localhost 5432
-- nc -zv localhost 5432

-- ---------------------------------------------------------------------------
-- 2. Migration conflicts
-- ---------------------------------------------------------------------------
-- Error message:
--   relation "schema_migrations" already exists
--   duplicate key value violates unique constraint "schema_migrations_pkey"
--   Migration V2__add_users has already been applied
--   FAILED: application of migration failed — column "email" of relation
--     "users" already exists
--
-- Cause:
--   - Running a migration that's already been applied
--   - Migration version number conflict (two migrations with same version)
--   - Migration checksum doesn't match (Flyway)
--   - Manual schema changes out of sync with migration files
--
-- Fixes:

-- Fix 1: Check migration history (Flyway)
-- SELECT version, description, installed_on, success FROM flyway_schema_history ORDER BY version;

-- Fix 2: Check migration history (Alembic)
-- SELECT * FROM alembic_version;

-- Fix 3: Mark a migration as applied without running it (Flyway)
-- flyway migrate -baselineOnMigrate=true
-- flyway baseline --baselineVersion=3
-- Or insert the record manually:
-- INSERT INTO flyway_schema_history
--   (installed_rank, version, description, type, script, checksum, installed_by, installed_on, execution_time, success)
-- VALUES (8, '4', 'add_users', 'SQL', 'V4__add_users.sql', NULL, 'admin', NOW(), 0, true);

-- Fix 4: Repair a failed migration (Flyway)
-- flyway repair

-- Fix 5: For Alembic, stamp the current state
-- alembic stamp head

-- Fix 6: Roll back then re-apply (if reversible)
-- alembic downgrade -1
-- alembic upgrade +1

-- ---------------------------------------------------------------------------
-- 3. Deadlocks
-- ---------------------------------------------------------------------------
-- Error message:
--   ERROR: deadlock detected
--   DETAIL: Process 123 waits for ShareLock on transaction 456; blocked by
--     process 789. Process 789 waits for ShareLock on transaction 123; blocked
--     by process 456.
--   HINT: See server log for query details.
--   ERROR: would deadlock
--
-- Cause:
--   - Two transactions lock resources in different orders
--   - Concurrent transactions acquiring overlapping row-level locks
--   - Long-running transactions conflicting with each other
--   - Missing indexes causing table-level locks instead of row-level
--
-- Fixes:

-- Fix 1: Set a lock timeout to fail fast instead of hanging
SET lock_timeout = '5s';
-- Or globally in postgresql.conf:
-- lock_timeout = 5000

-- Fix 2: Always acquire locks in the same order
-- ✅ Transaction A: UPDATE table1 THEN UPDATE table2
-- ✅ Transaction B: UPDATE table1 THEN UPDATE table2
-- ❌ Transaction A: UPDATE table1 THEN table2
-- ❌ Transaction B: UPDATE table2 THEN table1  ← deadlock!

-- Fix 3: Keep transactions short — commit as soon as possible
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;  -- Don't leave this open

-- Fix 4: Check for deadlocks
-- SELECT * FROM pg_locks WHERE NOT granted;
-- SELECT pg_blocking_pids(<pid>);
-- SELECT blocked.pid AS blocked_pid, blocker.pid AS blocker_pid
-- FROM pg_catalog.pg_locks blocked
-- JOIN pg_catalog.pg_locks blocker ON blocked.locktype = blocker.locktype
--   AND blocked.database = blocker.database
--   AND blocked.relation = blocker.relation
--   AND blocked.page = blocker.page
--   AND blocked.tuple = blocker.tuple
-- WHERE NOT blocked.granted;

-- Fix 5: Kill a blocking process (last resort)
-- SELECT pg_terminate_backend(<pid>);

-- Fix 6: Use NOWAIT or SKIP LOCKED to avoid waiting
-- SELECT * FROM jobs WHERE status = 'pending'
-- ORDER BY created_at LIMIT 1
-- FOR UPDATE SKIP LOCKED;

-- ---------------------------------------------------------------------------
-- 4. Duplicate key violation
-- ---------------------------------------------------------------------------
-- Error message:
--   ERROR: duplicate key value violates unique constraint "users_email_key"
--   DETAIL: Key (email)=(alice@example.com) already exists.
--   ERROR: duplicate key violates unique constraint "products_pkey"
--
-- Cause:
--   - INSERT violates a UNIQUE constraint on the column
--   - INSERT violates PRIMARY KEY uniqueness
--   - Sequence got out of sync (e.g., after restoring from backup)
--   - Race condition: concurrent inserts with same unique value
--
-- Fixes:

-- Fix 1: Use ON CONFLICT DO NOTHING (PostgreSQL)
INSERT INTO users (email, name)
VALUES ('alice@example.com', 'Alice')
ON CONFLICT (email) DO NOTHING;

-- Fix 2: Use ON CONFLICT DO UPDATE (upsert)
INSERT INTO users (email, name, updated_at)
VALUES ('alice@example.com', 'Alice', NOW())
ON CONFLICT (email) DO UPDATE
SET name = EXCLUDED.name,
    updated_at = EXCLUDED.updated_at;

-- Fix 3: Check before insert (less reliable — race condition window)
-- Not recommended under concurrent load — use ON CONFLICT instead

-- Fix 4: Fix sequence after restore (PostgreSQL)
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- Fix 5: For MySQL/MariaDB equivalent
-- INSERT INTO users (email, name) VALUES ('alice@example.com', 'Alice')
--   ON DUPLICATE KEY UPDATE name = VALUES(name);
-- INSERT IGNORE INTO users (email, name) VALUES ('alice@example.com', 'Alice');

-- ---------------------------------------------------------------------------
-- 5. Too many connections
-- ---------------------------------------------------------------------------
-- Error message:
--   FATAL: sorry, too many clients already
--   psql: error: connection to server at "localhost" (127.0.0.1), port 5432
--     failed: FATAL:  too many connections for database "mydb"
--   SQLSTATE[08004] [1040] Too many connections
--
-- Cause:
--   - Connection pool exhausted (max_connections reached)
--   - Application doesn't close connections properly (connection leak)
--   - Too many simultaneous clients for the configured max
--   - Stale connections from disconnected sessions
--
-- Fixes:

-- Fix 1: Kill idle connections (PostgreSQL)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < NOW() - INTERVAL '30 minutes'
  AND backend_type = 'client backend';

-- Fix 2: Check current connection count
SELECT count(*) FROM pg_stat_activity;
SELECT count(*) FROM pg_stat_activity WHERE datname = 'mydb';

-- Fix 3: Temporarily increase max_connections (then restart)
-- ALTER SYSTEM SET max_connections = 200;
-- Then restart PostgreSQL, or use:
-- SELECT pg_reload_conf();  -- (doesn't apply to max_connections)

-- Fix 4: Use a connection pooler (PgBouncer, pgpool-II)
-- pgbouncer.ini:
-- [databases]
-- mydb = host=localhost port=5432 dbname=mydb
-- [pgbouncer]
-- pool_mode = transaction
-- max_client_conn = 200
-- default_pool_size = 25

-- Fix 5: Set connection limits per user/database
ALTER USER app_user CONNECTION LIMIT 50;
ALTER DATABASE mydb CONNECTION LIMIT 100;

-- Fix 6: In the application, always close connections
-- Python (psycopg2):
-- conn.close()
-- Python (SQLAlchemy):
-- engine.dispose()
-- Node.js (pg):
-- client.end()

-- ---------------------------------------------------------------------------
-- 6. SSL/TLS handshake error
-- ---------------------------------------------------------------------------
-- Error message:
--   FATAL: no pg_hba.conf entry for host "...", user "...", database "...", SSL off
--   SSL error: certificate verify failed
--   could not translate host name "db.example.com" to address: Name or service not known
--   SSL SYSCALL error: EOF detected
--   The server does not support SSL connections
--
-- Cause:
--   - Server requires SSL but client is connecting without it
--   - SSL certificate expired or misconfigured
--   - Server certificate hostname doesn't match the connection host
--   - Self-signed certificate not trusted by client
--   - Server doesn't have SSL enabled but client is requesting it
--
-- Fixes:

-- Fix 1: Configure SSL mode in connection string
-- psql "sslmode=require host=db.example.com dbname=mydb"
-- psql "sslmode=verify-full host=db.example.com dbname=mydb"
-- sslmode options: disable, allow, prefer, require, verify-ca, verify-full

-- Fix 2: Client connection strings
-- PostgreSQL:
-- postgresql://user:pass@host:5432/db?sslmode=require
-- postgresql://user:pass@host:5432/db?sslmode=verify-full&sslcert=...&sslkey=...&sslrootcert=...

-- Fix 3: Check pg_hba.conf SSL requirements
-- # TYPE  DATABASE  USER      ADDRESS         METHOD
-- hostssl all       all       0.0.0.0/0       md5
-- ❌ host (without ssl) will be rejected for SSL-required databases

-- Fix 4: Regenerate or update certificates
-- Check expiration:
-- openssl x509 -in server.crt -noout -dates
-- openssl x509 -in server.crt -noout -subject -issuer

-- Fix 5: On the server, enable SSL in postgresql.conf
-- ssl = on
-- ssl_cert_file = '/etc/ssl/certs/server.crt'
-- ssl_key_file = '/etc/ssl/private/server.key'
-- ssl_ca_file = '/etc/ssl/certs/ca.crt'
-- Then restart: sudo systemctl restart postgresql
```