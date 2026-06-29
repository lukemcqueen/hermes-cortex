---
language: sql
tags: [postgres, connection, authentication, psql]
title: PostgreSQL Connection & Authentication
description: psql connection flags, pg_hba.conf rules, .pgpass file, and connection string URIs
source: pattern
---

```sql
-- psql connection flags
psql -h localhost -p 5432 -U myuser -d mydb
psql "postgresql://myuser:mypass@localhost:5432/mydb?sslmode=require"
psql -h /var/run/postgresql -U myuser mydb  # Unix socket

-- .pgpass file (~/.pgpass) format
-- hostname:port:database:username:password
localhost:5432:mydb:myuser:secret
*

-- pg_hba.conf authentication entries
# TYPE  DATABASE  USER        ADDRESS        METHOD
local   all       all                        peer
host    all       all         127.0.0.1/32   scram-sha-256
host    all       all         ::1/128        md5
hostssl all       all         0.0.0.0/0      cert

-- Connection string URI formats
postgresql://user:password@host:5432/dbname
postgresql://user@host:5432/dbname?sslmode=verify-full
postgresql:///dbname?host=/var/run/postgresql

-- Connection info queries
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
SELECT * FROM pg_stat_activity WHERE state = 'active';
SHOW port;
SHOW listen_addresses;
```