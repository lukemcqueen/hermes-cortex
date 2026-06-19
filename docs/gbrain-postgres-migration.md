# gbrain PGLite → PostgreSQL Migration Guide

## Problem

**Symptom:** gbrain autopilot/sync fails every 5 minutes with:
```
PGLite failed to initialize its WASM runtime.
Aborted(). Build with -sASSERTIONS for more info.
```

**Root Cause:** PGLite WASM runtime is incompatible with Linux glibc/kernel versions. This is a known upstream issue (garrytan/gbrain#223).

**Impact:** 
- gbrain knowledge sync/autopilot completely broken
- All gbrain-dependent Hermes features degraded
- Auto-remediation cannot fix (requires engine switch)

---

## Solution: Migrate to PostgreSQL Backend

PGLite is a WASM-embedded PostgreSQL designed for browsers/edge. For production Linux servers, use native PostgreSQL.

### Option A: Docker PostgreSQL (Recommended for cisnet02)

**1. Create PostgreSQL container:**
```bash
docker run -d \
  --name gbrain-postgres \
  -e POSTGRES_USER=gbrain \
  -e POSTGRES_PASSWORD=$(openssl rand -base64 24) \
  -e POSTGRES_DB=gbrain \
  -p 127.0.0.1:5433:5432 \
  -v gbrain-pgdata:/var/lib/postgresql/data \
  --restart unless-stopped \
  postgres:16-alpine
```

**2. Save credentials securely:**
```bash
# Get the generated password
docker exec gbrain-postgres env | grep POSTGRES_PASSWORD

# Store in secure location
echo "postgresql://gbrain:YOUR_PASSWORD@localhost:5433/gbrain" > ~/.hermes/private/gbrain-postgres-url.txt
chmod 600 ~/.hermes/private/gbrain-postgres-url.txt
```

**3. Migrate gbrain:**
```bash
# Stop gbrain autopilot
gbrain autopilot stop 2>/dev/null || true

# Backup existing PGLite data (optional, for safety)
cp -r ~/.gbrain ~/.gbrain.backup.pglite.$(date +%Y%m%d)

# Reinitialize with PostgreSQL engine
gbrain init --engine postgres --postgres-url 'postgresql://gbrain:YOUR_PASSWORD@localhost:5433/gbrain'

# Verify migration
gbrain doctor

# Restart autopilot
gbrain autopilot start
```

**4. Update cron job (if needed):**
The autopilot cron should automatically pick up the new config. Verify:
```bash
gbrain autopilot status
```

---

### Option B: System PostgreSQL (If Already Installed)

**1. Create database and user:**
```bash
sudo -u postgres psql <<EOF
CREATE USER gbrain WITH PASSWORD 'YOUR_PASSWORD';
CREATE DATABASE gbrain OWNER gbrain;
GRANT ALL PRIVILEGES ON DATABASE gbrain TO gbrain;
EOF
```

**2. Initialize gbrain:**
```bash
gbrain init --engine postgres --postgres-url 'postgresql://gbrain:YOUR_PASSWORD@localhost:5432/gbrain'
```

---

### Option C: External PostgreSQL (Cloud/Remote)

Use any PostgreSQL service (Neon, Supabase, RDS, etc.):

```bash
gbrain init --engine postgres --postgres-url 'postgresql://user:password@host:port/database'
```

---

## Verification

After migration, verify everything works:

**1. Check gbrain health:**
```bash
gbrain doctor
# Should show 90+ overall health score
# [OK] connection → Successfully connected to PostgreSQL
```

**2. Test sync:**
```bash
gbrain sync --all --no-pull
# Should complete without WASM errors
```

**3. Verify autopilot:**
```bash
gbrain autopilot status
# Should show "running" with recent heartbeat
```

**4. Check Hermes integration:**
```bash
# Wait for next cron cycle (5 minutes)
# Check cron output for successful runs
hermes cron list | grep -A 5 "autopilot\|sync"
```

---

## Rollback (If Needed)

If PostgreSQL migration fails, rollback to PGLite:

```bash
# Stop autopilot
gbrain autopilot stop

# Remove new config
rm -rf ~/.gbrain

# Restore backup
cp -r ~/.gbrain.backup.pglite.* ~/.gbrain

# Reinitialize PGLite
gbrain init --engine pglite

# Note: WASM issue will return, but data is preserved
```

---

## Post-Migration Cleanup

**1. Remove old PGLite data (after confirming PostgreSQL works):**
```bash
rm -rf ~/.gbrain.backup.pglite.*
```

**2. Update monitoring:**
The enhanced `remediation-sensor.py` will now report gbrain as healthy.

**3. Document connection string:**
Store PostgreSQL URL in secure location for future reference:
```bash
# ~/.hermes/private/gbrain-postgres-url.txt
# postgresql://gbrain:***@localhost:5433/gbrain
```

---

## Troubleshooting

### Connection Refused
```bash
# Check PostgreSQL is running
docker ps | grep gbrain-postgres
# or
systemctl status postgresql

# Check port binding
netstat -tlnp | grep 5433
```

### Permission Denied
```bash
# Ensure gbrain user can access config
chmod 600 ~/.gbrain/config.toml
```

### Migration Failures
```bash
# Check gbrain logs
gbrain doctor --verbose

# Check PostgreSQL logs
docker logs gbrain-postgres
# or
sudo tail -f /var/log/postgresql/postgresql-*.log
```

---

## Why PostgreSQL > PGLite for Production

| Aspect | PGLite | PostgreSQL |
|--------|--------|------------|
| **Runtime** | WASM in Bun/Node | Native binary |
| **Compatibility** | Browser/edge only | All platforms |
| **Performance** | ~10-50x slower | Native speed |
| **Memory** | Limited by WASM heap | System RAM |
| **Persistence** | File-based | Full ACID |
| **Extensions** | Limited (pgvector only) | Full ecosystem |
| **Production Ready** | ❌ No | ✅ Yes |

**Bottom line:** PGLite is for development/demo. PostgreSQL is for production.

---

## References

- Upstream issue: https://github.com/garrytan/gbrain/issues/223
- gbrain docs: https://gbrain.dev/docs/configuration
- PostgreSQL Docker: https://hub.docker.com/_/postgres
