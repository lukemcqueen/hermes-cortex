#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-profile-reader-role.sh
#
# Creates the per-profile mycortex reader role: mycortex_reader_<profile>.
# This is the schema-native multi-tenant design (Luke 2026-08-06 — "imagine
# 100 employees sharing one brain"):
#
#   mycortex_reader           ← base capability role (schema grants)
#   mycortex_reader_<profile> ← LOGIN INHERIT mycortex_reader (per-tenant)
#
# Two orthogonal axes, both enforced by the existing schema:
#   * What you may TOUCH  (schema)  → role membership inherits mycortex_reader's
#     SELECT on pages/chunks, EXECUTE on is_source_visible/log_query.
#   * What you may SEE    (data)    → RLS keys on CURRENT_USER; source_grants
#     rows are per-profile-role, so an un-granted profile sees ZERO rows.
#
# RLS policy (verified 2026-08-06):
#   USING (mycortex.is_source_visible(source_id, (CURRENT_USER)::text))
# → isolation is automatic once each profile connects as its own role.
#
# Role creation needs superuser (mycortex_admin has no CREATEROLE — verified
# f/f), so this connects as the `mycortex` superuser inside the container.
# Runs as a cortex-update.sh step AFTER migrate.py (DDL path), idempotent.
#
# Profile resolution (tenant boundary): HERMES_PROFILE env → AGENT_NAME →
# fail loudly. macOS uses direct psql (no container).
#
# ⚠️ SQL is piped via STDIN (heredoc), never -c "$SQL" through nested
#    double-quoted sg docker -c: $$ would re-expand to the shell PID at
#    interpolation (observed 2026-08-06: 'DO 2640698' syntax error).
# ───────────────────────────────────────────────────────────────
set -euo pipefail

HOME_DIR="${HOME:?}"
HERMES_HOME="${HERMES_HOME:-${HOME_DIR}/.hermes}"

# ── Resolve profile (tenant boundary: PROFILE, not hostname) ──
# Reliable order: HERMES_PROFILE (gateway sets this for named profiles) →
# AGENT_NAME → FAIL LOUDLY. ⚠️ Do NOT scan ~/.hermes/profiles/*/ — the first
# entry alphabetically is NOT the active profile (observed 2026-08-06:
# 'personal' dir exists but the session runs as 'default'/esther; the scan
# picked the wrong tenant and created mycortex_reader_personal). ⚠️ NEVER
# fall back to hostname — a machine name is not a tenant identity and would
# create a garbage mycortex_reader_<hostname> role (Luke directive 2026-08-14).
PROFILE="${HERMES_PROFILE:-}"
if [[ -z "$PROFILE" ]]; then
  PROFILE="${AGENT_NAME:-}"
fi
if [[ -z "$PROFILE" ]]; then
  echo "❌ Cannot resolve profile: HERMES_PROFILE and AGENT_NAME are both unset." >&2
  echo "   Set AGENT_NAME= in ~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME" >&2
  exit 1
fi

READER_ROLE="mycortex_reader_${PROFILE}"
echo "install-profile-reader-role: ensuring ${READER_ROLE} (profile=${PROFILE})"

# ── SQL: create role if missing, grant base-reader membership ──
# PG has no CREATE ROLE IF NOT EXISTS — DO block guard instead.
# Heredoc (quoted 'EOF') → no shell expansion; piped via stdin.
SQL_FILE="$(mktemp)"
trap 'rm -f "$SQL_FILE"' EXIT
cat > "$SQL_FILE" <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${READER_ROLE}') THEN
    CREATE ROLE ${READER_ROLE} LOGIN INHERIT;
    GRANT mycortex_reader TO ${READER_ROLE};
  END IF;
END
\$\$;
EOF

if [[ "$(uname -s)" == "Darwin" ]]; then
  psql_bin="$(command -v psql || echo /opt/homebrew/bin/psql)"
  "$psql_bin" -U mycortex -d mycortex -v ON_ERROR_STOP=1 < "$SQL_FILE" >/dev/null
elif command -v sg >/dev/null 2>&1; then
  sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1" < "$SQL_FILE" >/dev/null
else
  docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1 < "$SQL_FILE" >/dev/null
fi

# ── Migrate legacy grants: shared reader → profile role (idempotent) ──
# Pre-2026-08-06 hosts granted ISOLATED sources to the shared mycortex_reader.
# After this change the CLI connects as mycortex_reader_<profile>, so those
# grants would make the host's OWN sources invisible (profile role has no
# grant → RLS shows zero rows). Migrate any remaining shared-reader grants
# on non-federated sources to this host's profile role. Idempotent: after
# the first run no mycortex_reader rows remain, so the UPDATE is a no-op.
MIGRATE_SQL="UPDATE mycortex.source_grants g
SET role_name = '${READER_ROLE}'
WHERE role_name = 'mycortex_reader'
  AND source_id IN (
    SELECT id FROM mycortex.sources
    WHERE NOT archived AND NOT is_federated
  );"

cat > "$SQL_FILE" <<EOF
${MIGRATE_SQL}
EOF

if [[ "$(uname -s)" == "Darwin" ]]; then
  "$psql_bin" -U mycortex -d mycortex -v ON_ERROR_STOP=1 < "$SQL_FILE" >/dev/null
elif command -v sg >/dev/null 2>&1; then
  sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1" < "$SQL_FILE" >/dev/null
else
  docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1 < "$SQL_FILE" >/dev/null
fi

echo "install-profile-reader-role: ${READER_ROLE} ready (inherits mycortex_reader schema grants; legacy shared-reader grants migrated)"
