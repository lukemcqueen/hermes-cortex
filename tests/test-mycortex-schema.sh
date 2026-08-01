#!/usr/bin/env bash
# test-mycortex-schema.sh — S-003 AC battery for the mycortex schema v001
#
# Covers (from docs/elicit/2026-08-01_mycortex-stories.md S-003):
#   AC1  fresh DB → migrate.py → schema + roles + RLS exist; re-run = no-op
#   AC3  mycortex_reader → only federated sources visible without grant (RLS FORCE)
#   AC4  isolated source, reader without grant → zero rows (isolation-leak test
#       runs as mycortex_reader, NOT superuser)
#   AC5  is_federated=true without pii_scan_at → CHECK constraint rejects
#   AC6  mycortex_ingest UPDATE on sources → permission denied (role split)
#
# Uses a scratch database `mycortex_test` — NEVER touches the `gbrain` DB
# (hermeticity guard: fails fast if MIGRATE_TARGET resolves to gbrain).
#
# Run: bash tests/test-mycortex-schema.sh
set -eu
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATE_PY="${REPO_DIR}/ops/services/mycortex/migrate.py"
TEST_DB="${MYCORTEX_TEST_DB:-mycortex_test}"

if [[ "$TEST_DB" == "gbrain" ]]; then
  echo "❌ REFUSING to run against the gbrain DB — hermeticity guard. Set MYCORTEX_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec gbrain-postgres psql -U gbrain -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec gbrain-postgres psql -U gbrain -d gbrain -t -A"

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  $PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo ""
echo "═══ Setup: scratch DB ${TEST_DB} ═══"
$PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
$PSQL_SUPER -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1
echo "  created ${TEST_DB}"

echo ""
echo "═══ AC1: Fresh DB → migrate.py creates schema + roles + RLS; re-run no-op ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  pass "migrate.py applies v001 on fresh DB"
else
  fail "migrate.py failed on fresh DB"
fi

SCHEMA_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.schemata WHERE schema_name='mycortex';" 2>/dev/null)
[ "$SCHEMA_EXISTS" = "1" ] && pass "mycortex schema exists" || fail "mycortex schema missing (got: $SCHEMA_EXISTS)"

RLS_FORCE=$($PSQL -c "SELECT count(*) FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname='mycortex' AND p.polpermissive=false;" 2>/dev/null)
# Policies in PG 17 are permissive by default; FORCE is on the table, not the policy.
FORCE_PAGES=$($PSQL -c "SELECT relforcerowsecurity FROM pg_class WHERE oid='mycortex.pages'::regclass;" 2>/dev/null)
FORCE_CHUNKS=$($PSQL -c "SELECT relforcerowsecurity FROM pg_class WHERE oid='mycortex.content_chunks'::regclass;" 2>/dev/null)
[ "$FORCE_PAGES" = "t" ] && pass "pages FORCE ROW LEVEL SECURITY" || fail "pages FORCE RLS missing (got: $FORCE_PAGES)"
[ "$FORCE_CHUNKS" = "t" ] && pass "content_chunks FORCE ROW LEVEL SECURITY" || fail "chunks FORCE RLS missing (got: $FORCE_CHUNKS)"

POLICY_COUNT=$($PSQL -c "SELECT count(*) FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname='mycortex';" 2>/dev/null)
[ "$POLICY_COUNT" -ge 2 ] && pass "${POLICY_COUNT} RLS policies exist" || fail "expected ≥2 policies, got $POLICY_COUNT"

if python3 "$MIGRATE_PY" --db-name "$TEST_DB" 2>/dev/null | grep -q "no-op"; then
  pass "re-run is a no-op (schema_version gated)"
else
  fail "re-run did not report no-op"
fi
VER=$($PSQL -c "SELECT max(version) FROM mycortex.schema_version;" 2>/dev/null)
[ "$VER" = "1" ] && pass "schema_version = 1" || fail "schema_version = $VER (expected 1)"

echo ""
echo "═══ Seed: federated + isolated sources with pages ═══"
FED_ID=$($PSQL -c "INSERT INTO mycortex.sources (name, local_path, is_federated, pii_scan_at) VALUES ('hermes-test', '/tmp/hermes', TRUE, now()) RETURNING id;" 2>/dev/null | head -1)
ISO_ID=$($PSQL -c "INSERT INTO mycortex.sources (name, local_path, is_federated) VALUES ('moses-test', '/tmp/moses', FALSE) RETURNING id;" 2>/dev/null | head -1)
PAGE_FED=$($PSQL -c "INSERT INTO mycortex.pages (source_id, relpath, title, content_hash) VALUES ('${FED_ID}', 'docs/fed.md', 'Federated Page', 'abc123') RETURNING id;" 2>/dev/null | head -1)
PAGE_ISO=$($PSQL -c "INSERT INTO mycortex.pages (source_id, relpath, title, content_hash) VALUES ('${ISO_ID}', 'private/iso.md', 'Isolated Page', 'def456') RETURNING id;" 2>/dev/null | head -1)
$PSQL -c "INSERT INTO mycortex.content_chunks (page_id, chunk_index, content) VALUES ('${PAGE_FED}', 0, 'federated chunk text');" >/dev/null 2>&1
$PSQL -c "INSERT INTO mycortex.content_chunks (page_id, chunk_index, content) VALUES ('${PAGE_ISO}', 0, 'isolated chunk text');" >/dev/null 2>&1
echo "  federated source=${FED_ID:0:8} page=${PAGE_FED:0:8} | isolated source=${ISO_ID:0:8} page=${PAGE_ISO:0:8}"

echo ""
echo "═══ AC3+AC4: Reader sees federated ONLY; isolation-leak test AS mycortex_reader ═══"
READER_PSQL="docker exec gbrain-postgres psql -U mycortex_reader -d ${TEST_DB} -t -A"

FED_VISIBLE=$($READER_PSQL -c "SELECT count(*) FROM mycortex.pages;" 2>/dev/null)
[ "$FED_VISIBLE" = "1" ] && pass "reader sees exactly the federated page (got $FED_VISIBLE)" || fail "reader sees $FED_VISIBLE pages (expected 1 — isolation leak?)"

ISO_LEAK=$($READER_PSQL -c "SELECT count(*) FROM mycortex.pages p JOIN mycortex.sources s ON s.id=p.source_id WHERE s.name='moses-test';" 2>/dev/null)
[ "$ISO_LEAK" = "0" ] && pass "isolated source invisible without grant (isolation-leak test as reader)" || fail "ISOLATION LEAK: reader saw $ISO_LEAK isolated rows"

CHUNK_LEAK=$($READER_PSQL -c "SELECT count(*) FROM mycortex.content_chunks c JOIN mycortex.pages p ON p.id=c.page_id JOIN mycortex.sources s ON s.id=p.source_id WHERE s.name='moses-test';" 2>/dev/null)
[ "$CHUNK_LEAK" = "0" ] && pass "isolated chunks invisible without grant" || fail "CHUNK LEAK: reader saw $CHUNK_LEAK isolated chunks"

echo ""
echo "═══ AC3b: grant → reader sees isolated source ═══"
$PSQL -c "INSERT INTO mycortex.source_grants (role_name, source_id) VALUES ('mycortex_reader', '${ISO_ID}');" >/dev/null 2>&1
ISO_GRANTED=$($READER_PSQL -c "SELECT count(*) FROM mycortex.pages p JOIN mycortex.sources s ON s.id=p.source_id WHERE s.name='moses-test';" 2>/dev/null)
[ "$ISO_GRANTED" = "1" ] && pass "granted reader sees isolated source (got $ISO_GRANTED)" || fail "granted reader sees $ISO_GRANTED (expected 1)"

echo ""
echo "═══ AC5: PII gate CHECK — federated without pii_scan_at rejected ═══"
if $PSQL -c "INSERT INTO mycortex.sources (name, local_path, is_federated) VALUES ('leak-test', '/tmp/leak', TRUE);" >/dev/null 2>&1; then
  fail "CHECK constraint did NOT reject federated-without-PII-scan"
else
  pass "is_federated=true without pii_scan_at rejected by CHECK"
fi

echo ""
echo "═══ AC6: Role split — mycortex_ingest cannot UPDATE sources ═══"
INGEST_PSQL="docker exec gbrain-postgres psql -U mycortex_ingest -d ${TEST_DB} -t -A"
if $INGEST_PSQL -c "UPDATE mycortex.sources SET is_federated=TRUE WHERE name='moses-test';" >/dev/null 2>&1; then
  fail "mycortex_ingest UPDATEd sources — role split BROKEN"
else
  pass "mycortex_ingest UPDATE on sources denied (permission denied)"
fi

# ingest CAN insert pages (its legitimate job)
if $INGEST_PSQL -c "INSERT INTO mycortex.pages (source_id, relpath, title, content_hash) VALUES ('${ISO_ID}', 'ingest/ok.md', 'Ingest OK', '123abc');" >/dev/null 2>&1; then
  pass "mycortex_ingest CAN insert pages (DML scope intact)"
else
  fail "mycortex_ingest cannot insert pages — scope too narrow"
fi

# reader cannot write query_log / see query_log
if $READER_PSQL -c "SELECT count(*) FROM mycortex.query_log;" >/dev/null 2>&1; then
  fail "reader CAN read query_log — REVOKE broken"
else
  pass "reader cannot SELECT query_log (REVOKE enforced)"
fi

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
[ "$F" -eq 0 ] || echo "  ❌ SOME TESTS FAILED — investigate before shipping"
exit $F
