#!/usr/bin/env bash
# migrate-gbrain-postgres-to-mycortex.sh — one-shot per-host migration
#
# Moves a host from the old `gbrain-postgres` container (db `gbrain`, role
# `gbrain`, langfuse-owned volume) to the dedicated hermes-cortex-owned
# `mycortex-postgres` container (db `mycortex`, role `mycortex`).
#
# WHY: the knowledge brain + agent bus previously ran on a container that
# carried stale langfuse compose labels and a langfuse-named volume. This
# script is the fleet rollout for the 2026-08-05 migration (repo commit
# 332d1e3e). Esther's host was migrated manually as the reference; this is
# the repeatable version for joseph / gisu / kustos / titus / moses.
#
# PLATFORMS: Linux and macOS (Docker Desktop). The script uses `docker`
# exec/compose/inspect only — no systemd-specific commands beyond an
# optional, fails-safe `systemctl` check for the bus stop (skipped when
# systemctl is absent, i.e. macOS). macOS hosts (Titus) run the same
# container via Docker Desktop; the mycortex CLI's Darwin branch connects
# via direct psql (env → ~/.hermes-cortex/mycortex.conf → legacy
# ~/.gbrain/config.json → defaults) and is already updated for `mycortex`.
# Portability: no `seq`/`timeout`/GNU-only utilities (verified 2026-08-05).
#
# IDEMPOTENT: safe to re-run. Detects an already-migrated host and exits 0.
# Non-destructive: the old container is STOPPED, not removed, so rollback is
# `docker start gbrain-postgres` + revert the .env lines this script changed.
#
# USAGE:
#   bash migrate-gbrain-postgres-to-mycortex.sh [--dry-run] [--yes]
#
#   --dry-run  print the plan, make NO changes
#   --yes      skip the interactive confirmation prompt
#
# BEFORE RUNNING (recommended, not required):
#   hermes cron pause agent-mycortex-sync agent-mycortex-retention
#   (a missed sync tick during the swap is harmless — the next tick recovers —
#    but pausing avoids a 15-min error alert)
#
# WHAT IT DOES:
#   1. Dump all schemas from gbrain-postgres (bus, mycortex, public legacy)
#   2. Stop the bus server (orchestrators only) — releases the gbrain conn
#   3. Stop gbrain-postgres (frees port 15432)
#   4. Start mycortex-postgres via docker-compose.mycortex.yml
#   5. Restore the dump (--no-owner --no-privileges) into db `mycortex`
#   6. Re-apply cluster roles + RLS policies + grants (embedded, verified)
#   7. Update connection strings: ~/hermes-cortex/.env CORTEX_BUS_PG_*,
#      ~/.hermes-cortex/.env MYCORTEX_PG_PASSWORD, ~/.gbrain/config.json
#   8. Restart the bus, verify mycortex doctor + page counts + search
#
# VERIFY AFTER: bash ~/.hermes-cortex/scripts/mycortex doctor --json
#   hermes cron resume agent-mycortex-sync agent-mycortex-retention

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────
CORTEX_HOME="${HOME}"
DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${CORTEX_HOME}/.hermes-cortex}"
REPO="${CORTEX_HOME}/hermes-cortex"
OLD_CONTAINER="gbrain-postgres"
NEW_CONTAINER="mycortex-postgres"
OLD_DB="gbrain"
NEW_DB="mycortex"
OLD_ROLE="gbrain"
NEW_ROLE="mycortex"
BUS_PORT=15432
COMPOSE_SRC="${REPO}/ops/install/deploy/docker-compose.mycortex.yml"
COMPOSE_DST="${DEPLOY_HOME}/docker-compose.mycortex.yml"
DEPLOY_ENV="${DEPLOY_HOME}/.env"
BUS_ENV="${CORTEX_HOME}/hermes-cortex/.env"
BACKUP_DIR="${DEPLOY_HOME}/backups"
TS="$(date +%Y%m%d-%H%M%S)"
DUMP="${BACKUP_DIR}/gbrain-migration-${TS}.dump"
REAPPLY_SQL="${BACKUP_DIR}/reapply-roles-policies-grants-${TS}.sql"

DRY_RUN=false
ASSUME_YES=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --yes)     ASSUME_YES=true ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '%s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }
die()  { printf '❌ %s\n' "$*" >&2; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────
docker_exec() { # docker_exec <container> <role> <db> <sql>
  docker exec -i "$1" psql -U "$2" -d "$3" -v ON_ERROR_STOP=1 -t -A -c "$4" 2>/dev/null
}

container_running() { docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }
container_exists()  { docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }

# ── State detection (idempotency) ─────────────────────────────────
log "━━━ gbrain-postgres → mycortex-postgres migration ━━━"
log "host: $(hostname)   user: ${USER}"
log ""

command -v docker >/dev/null 2>&1 || die "docker not found — this migration targets docker-based hosts (Linux + docker macOS)."

if ! container_exists "$OLD_CONTAINER" && ! container_exists "$NEW_CONTAINER"; then
  log "✅ Nothing to migrate — neither gbrain-postgres nor mycortex-postgres exists on this host."
  exit 0
fi

if container_exists "$NEW_CONTAINER" && ! container_exists "$OLD_CONTAINER"; then
  log "✅ Already migrated — mycortex-postgres present, no gbrain-postgres."
  log "   (If the index is empty, re-run after restoring from a backup dump.)"
  exit 0
fi

if container_running "$NEW_CONTAINER"; then
  pages=$(docker_exec "$NEW_CONTAINER" "$NEW_ROLE" "$NEW_DB" \
    "SELECT count(*) FROM mycortex.pages;" 2>/dev/null || echo "0")
  if [ "${pages:-0}" -gt 0 ]; then
    log "✅ Already migrated — mycortex-postgres running with ${pages} pages indexed."
    log "   Old container ${OLD_CONTAINER} is $(container_running "$OLD_CONTAINER" && echo RUNNING || echo stopped)."
    exit 0
  fi
  warn "mycortex-postgres exists but has 0 pages — proceeding with full migration."
fi

# ── Plan ──────────────────────────────────────────────────────────
log "Plan:"
log "  1. pg_dump ${OLD_CONTAINER}/${OLD_DB} → ${DUMP}"
log "  2. stop bus server (if running)"
log "  3. stop ${OLD_CONTAINER}, start ${NEW_CONTAINER} on port ${BUS_PORT}"
log "  4. pg_restore into ${NEW_DB} + re-apply roles/policies/grants"
log "  5. update connection strings (.env CORTEX_BUS_PG_*, MYCORTEX_PG_PASSWORD)"
log "  6. restart bus, verify doctor + counts + search"
log ""
if [ "$DRY_RUN" = true ]; then
  log "🔎 DRY RUN — no changes made."
  exit 0
fi
if [ "$ASSUME_YES" != true ]; then
  printf "Proceed? [y/N] "; read -r ans
  case "$ans" in y|Y|yes|YES) ;; *) log "aborted."; exit 1 ;; esac
fi

# ── 1. Dump ───────────────────────────────────────────────────────
container_running "$OLD_CONTAINER" || die "${OLD_CONTAINER} is not running — start it first: docker start ${OLD_CONTAINER}"
mkdir -p "$BACKUP_DIR"
log "📦 Dumping ${OLD_CONTAINER}/${OLD_DB} ..."
docker exec "$OLD_CONTAINER" pg_dump -U "$OLD_ROLE" -d "$OLD_DB" -Fc -f /tmp/gbrain-migration.dump \
  || die "pg_dump failed"
docker cp "${OLD_CONTAINER}:/tmp/gbrain-migration.dump" "$DUMP" >/dev/null 2>&1
docker exec "$OLD_CONTAINER" rm -f /tmp/gbrain-migration.dump 2>/dev/null || true
[ -s "$DUMP" ] || die "dump file empty — aborting before any change"
log "   → $(du -h "$DUMP" | cut -f1) saved to $DUMP"

# ── 2. Stop bus ───────────────────────────────────────────────────
if systemctl --user list-unit-files 2>/dev/null | grep -q '^cortex-bus.service'; then
  if systemctl --user is-active cortex-bus >/dev/null 2>&1; then
    log "🛑 Stopping cortex-bus (releases the gbrain DB connection) ..."
    systemctl --user stop cortex-bus
  else
    log "ℹ️  cortex-bus not active — nothing to stop."
  fi
else
  log "ℹ️  No cortex-bus unit (worker host) — skipping bus stop."
fi

# ── 3. Container swap ─────────────────────────────────────────────
log "🛑 Stopping ${OLD_CONTAINER} ..."
docker stop "$OLD_CONTAINER" >/dev/null

log "🚀 Starting ${NEW_CONTAINER} ..."
[ -f "$COMPOSE_DST" ] || {
  if [ -f "$COMPOSE_SRC" ]; then
    cp "$COMPOSE_SRC" "$COMPOSE_DST"
  else
    die "compose file missing: $COMPOSE_DST (expected from repo or previous deploy)"
  fi
}
# Ensure MYCORTEX_PG_PASSWORD exists — reuse GBRAIN_PG_PASSWORD / CORTEX_BUS_PG_PASS
# value if present, else generate a fresh one (the bus pass stays unchanged).
if ! grep -q '^MYCORTEX_PG_PASSWORD=' "$DEPLOY_ENV" 2>/dev/null; then
  OLD_PASS=""
  if [ -f "$DEPLOY_ENV" ]; then
    OLD_PASS="$(grep '^GBRAIN_PG_PASSWORD=' "$DEPLOY_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  if [ -z "$OLD_PASS" ] && [ -f "$BUS_ENV" ]; then
    OLD_PASS="$(grep '^CORTEX_BUS_PG_PASS=' "$BUS_ENV" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  if [ -n "$OLD_PASS" ]; then
    printf 'MYCORTEX_PG_PASSWORD=%s\n' "$OLD_PASS" >> "$DEPLOY_ENV"
    log "   MYCORTEX_PG_PASSWORD added to $DEPLOY_ENV (reused existing secret)"
  else
    printf 'MYCORTEX_PG_PASSWORD=%s\n' "$(openssl rand -hex 20)" >> "$DEPLOY_ENV"
    log "   MYCORTEX_PG_PASSWORD generated in $DEPLOY_ENV"
  fi
  chmod 600 "$DEPLOY_ENV"
fi

(
  cd "$DEPLOY_HOME" && docker compose -f docker-compose.mycortex.yml up -d 2>&1
) | sed 's/^/   /'

i=0
while [ "$i" -lt 30 ]; do
  i=$((i + 1))
  s="$(docker inspect --format '{{.State.Health.Status}}' "$NEW_CONTAINER" 2>/dev/null || echo starting)"
  [ "$s" = "healthy" ] && break
  sleep 2
done
[ "$(docker inspect --format '{{.State.Health.Status}}' "$NEW_CONTAINER" 2>/dev/null || echo unhealthy)" = "healthy" ] \
  || die "${NEW_CONTAINER} did not become healthy"

# ── 4. Restore + re-apply ─────────────────────────────────────────
log "📥 Restoring dump into ${NEW_DB} (no owner/privileges — re-applied below) ..."
docker exec -i "$NEW_CONTAINER" pg_restore -U "$NEW_ROLE" -d "$NEW_DB" \
  --no-owner --no-privileges < "$DUMP" 2>&1 | grep -v '^pg_restore: error: could not execute query: ERROR:  role' | sed 's/^/   /' || true

cat > "$REAPPLY_SQL" <<'SQLEOF'
-- Re-apply cluster roles + RLS policies + grants after --no-owner restore.
-- Source of truth: ops/services/mycortex/schema/mycortex.sql + v002 + v003.
DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_admin') THEN CREATE ROLE mycortex_admin LOGIN; END IF; END $$;
DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_ingest') THEN CREATE ROLE mycortex_ingest LOGIN; END IF; END $$;
DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_reader') THEN CREATE ROLE mycortex_reader LOGIN; END IF; END $$;

ALTER TABLE mycortex.pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.pages FORCE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks FORCE ROW LEVEL SECURITY;

CREATE POLICY mycortex_pages_select ON mycortex.pages
    FOR SELECT TO mycortex_reader
    USING (mycortex.is_source_visible(pages.source_id, current_user));
CREATE POLICY mycortex_chunks_select ON mycortex.content_chunks
    FOR SELECT TO mycortex_reader
    USING (EXISTS (SELECT 1 FROM mycortex.pages p WHERE p.id = content_chunks.page_id AND mycortex.is_source_visible(p.source_id, current_user)));
CREATE POLICY mycortex_pages_ingest ON mycortex.pages
    FOR ALL TO mycortex_ingest USING (true) WITH CHECK (true);
CREATE POLICY mycortex_chunks_ingest ON mycortex.content_chunks
    FOR ALL TO mycortex_ingest USING (true) WITH CHECK (true);
CREATE POLICY mycortex_pages_admin ON mycortex.pages
    FOR SELECT TO mycortex_admin USING (true);
CREATE POLICY mycortex_chunks_admin ON mycortex.content_chunks
    FOR SELECT TO mycortex_admin USING (true);

REVOKE SELECT ON mycortex.query_log FROM mycortex_reader;
REVOKE ALL ON mycortex.query_log FROM mycortex_ingest;
REVOKE ALL ON FUNCTION mycortex.log_query(TEXT, TEXT, TEXT[], INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.log_query(TEXT, TEXT, TEXT[], INT) TO mycortex_reader;
REVOKE ALL ON FUNCTION mycortex.is_source_visible(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.is_source_visible(UUID, TEXT) TO mycortex_reader;
GRANT USAGE ON SCHEMA mycortex TO mycortex_admin, mycortex_ingest, mycortex_reader;
GRANT CREATE ON SCHEMA mycortex TO mycortex_admin;
GRANT ALL ON mycortex.sources, mycortex.source_grants TO mycortex_admin;
GRANT SELECT ON mycortex.pages, mycortex.content_chunks, mycortex.ingest_log, mycortex.schema_version TO mycortex_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON mycortex.pages, mycortex.content_chunks, mycortex.ingest_log TO mycortex_ingest;
GRANT USAGE ON SEQUENCE mycortex.ingest_log_id_seq TO mycortex_ingest;
REVOKE ALL ON mycortex.sources, mycortex.source_grants, mycortex.query_log, mycortex.schema_version FROM mycortex_ingest;
GRANT SELECT ON mycortex.pages, mycortex.content_chunks TO mycortex_reader;
GRANT SELECT (id, name, is_federated, search_config) ON mycortex.sources TO mycortex_reader;
GRANT SELECT ON mycortex.schema_version TO mycortex_admin;
SQLEOF
log "🔧 Re-applying roles/policies/grants ..."
docker exec -i "$NEW_CONTAINER" psql -U "$NEW_ROLE" -d "$NEW_DB" -v ON_ERROR_STOP=1 -f - < "$REAPPLY_SQL" >/dev/null 2>&1 \
  || die "re-apply SQL failed (see $REAPPLY_SQL)"

# ── 4b. Fleet command verifications (hc send verification ledger) ──
# The bus schema files are applied manually at setup (not auto-deployed).
# Ensure the command-verifications DDL is present so `hc send`'s
# record_dispatch() call succeeds on the migrated host. Idempotent.
if [ -f "${REPO}/core/cortex_bus/schema/command-verifications.sql" ]; then
  log "🔧 Installing bus.command_verifications (record_dispatch) ..."
  docker exec -i "$NEW_CONTAINER" psql -U "$NEW_ROLE" -d "$NEW_DB" \
    -v ON_ERROR_STOP=1 -f - < "${REPO}/core/cortex_bus/schema/command-verifications.sql" >/dev/null 2>&1 \
    || warn "command-verifications.sql failed to apply (hc send verification will warn — non-fatal)"
elif [ -f "${DEPLOY_HOME}/core/cortex_bus/schema/command-verifications.sql" ]; then
  docker exec -i "$NEW_CONTAINER" psql -U "$NEW_ROLE" -d "$NEW_DB" \
    -v ON_ERROR_STOP=1 -f - < "${DEPLOY_HOME}/core/cortex_bus/schema/command-verifications.sql" >/dev/null 2>&1 \
    || warn "command-verifications.sql failed to apply (hc send verification will warn — non-fatal)"
else
  warn "command-verifications.sql not found (repo or deploy) — hc send verification will warn; non-fatal"
fi

# ── 5. Connection strings ─────────────────────────────────────────
log "🔗 Updating connection strings ..."
if [ -f "$BUS_ENV" ]; then
  python3 - "$BUS_ENV" <<'PYEOF'
import re, sys
p = sys.argv[1]
t = open(p).read()
for k, old, new in [("CORTEX_BUS_PG_DB", "gbrain", "mycortex"),
                    ("CORTEX_BUS_PG_USER", "gbrain", "mycortex")]:
    if re.search(rf'^{k}=', t, re.M):
        t = re.sub(rf'^{k}=.+$', f'{k}={new}', t, flags=re.M)
    else:
        t += f"\n{k}={new}\n"
open(p, "w").write(t)
print(f"  updated {p}")
PYEOF
fi

if [ -f "${CORTEX_HOME}/.gbrain/config.json" ]; then
  python3 - "${CORTEX_HOME}/.gbrain/config.json" <<'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
u = cfg.get("database_url", "")
if u and "/gbrain" in u:
    cfg["database_url"] = u.replace("/gbrain", "/mycortex").replace("://gbrain:", "://mycortex:")
    json.dump(cfg, open(p, "w"), indent=4)
    print("  updated ~/.gbrain/config.json database_url")
PYEOF
fi

# ── 6. Restart bus + verify ───────────────────────────────────────
if systemctl --user list-unit-files 2>/dev/null | grep -q '^cortex-bus.service'; then
  log "▶️  Restarting cortex-bus ..."
  systemctl --user start cortex-bus
  sleep 4
  if systemctl --user is-active cortex-bus >/dev/null 2>&1; then
    log "   cortex-bus active"
  else
    warn "cortex-bus failed to start — check: journalctl --user -u cortex-bus -n 50"
  fi
fi

log ""
log "━━━ Verification ━━━"
if [ -x "${DEPLOY_HOME}/scripts/mycortex" ]; then
  "${DEPLOY_HOME}/scripts/mycortex" doctor --json 2>&1 | tail -1 | sed 's/^/  /'
  "${DEPLOY_HOME}/scripts/mycortex" stats --json 2>&1 | head -8 | sed 's/^/  /'
else
  warn "mycortex CLI not at ${DEPLOY_HOME}/scripts/mycortex — run cortex-update.sh then verify manually"
fi

echo "  pages: $(docker_exec "$NEW_CONTAINER" "$NEW_ROLE" "$NEW_DB" "SELECT count(*) FROM mycortex.pages;" 2>/dev/null || echo '?')"
echo "  chunks: $(docker_exec "$NEW_CONTAINER" "$NEW_ROLE" "$NEW_DB" "SELECT count(*) FROM mycortex.content_chunks;" 2>/dev/null || echo '?')"
echo "  rls policies: $(docker_exec "$NEW_CONTAINER" "$NEW_ROLE" "$NEW_DB" "SELECT count(*) FROM pg_policies WHERE schemaname='mycortex';" 2>/dev/null || echo '?')"

log ""
log "✅ Migration complete on $(hostname)."
log "   Old container ${OLD_CONTAINER} is STOPPED (rollback: docker start ${OLD_CONTAINER} + revert .env)."
log "   Dump: ${DUMP}"
log ""
log "   NEXT: hermes cron resume agent-mycortex-sync agent-mycortex-retention"
log "   And run the doctor: python3 ${DEPLOY_HOME}/scripts/cortex-doctor.py --quiet"
exit 0
