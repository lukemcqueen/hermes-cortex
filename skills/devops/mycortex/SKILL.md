---
name: mycortex
version: 1.0.0
category: devops
description: "Use for mycortex knowledge brain work or gbrain migration."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# mycortex — Knowledge Brain (gbrain Replacement)

The fleet knowledge brain replacing gbrain: markdown-in-git as source of truth,
shared `gbrain-postgres` (:15432) as the query index, thin Python CLI + cron as
plumbing. No daemon, no bun. Canonical design: `docs/design/mycortex-DESIGN.md`;
stories: `docs/elicit/2026-08-01_mycortex-stories.md`.

## Architecture

| Layer | Choice |
|---|---|
| Source of truth | Markdown in git (`~/brain/*`, `~/hermes-cortex`) |
| Index store | `mycortex` schema on `gbrain-postgres` :15432 (pgvector for v1.1) |
| Search | Postgres FTS (`websearch_to_tsquery`) + pg_texample (v1); pgvector (v1.1 slice) |
| Plumbing | Cron sync (no daemon), advisory-lock guarded |

**Role split (DB-enforced, NOT CLI convention):**
| Role | Grants | Used by |
|---|---|---|
| `mycortex_admin` | sources/source_grants/DDL + full page SELECT (audit) | orchestrators — registration, PII gate, grants |
| `mycortex_ingest` | DML on pages/content_chunks/ingest_log ONLY; REVOKEd on sources | sync cron |
| `mycortex_reader` | SELECT on pages/chunks (RLS-filtered), sources(id,name,is_federated,search_config) | fleet agents via CLI |

RLS is FORCE'd on pages/content_chunks, fail-closed from v001: a reader sees a
page iff its source is federated OR the reader holds a `source_grants` row.
PII gate: `is_federated = TRUE` requires `pii_scan_at` (CHECK constraint).

## CLI (`ops/scripts/manage/mycortex`, deployed to `~/.hermes-cortex/scripts/mycortex`)

```
mycortex sources add <name> <path> [--mode git|local] [--federated] [--search-config C]
mycortex sources list [--json]
mycortex sources remove <name>          # builtin 'default' refused; pages hard-purge
mycortex sync [--source NAME] [--force] # sha256, advisory-lock, mass-delete guardrail
mycortex search <query> [--source NAME...] [--limit N] [--json]
mycortex list [-n N] [--source NAME] [--json]
mycortex stats [--json]
mycortex doctor [--json]
```

**Connection:** psql via `sg docker -c "docker exec -i gbrain-postgres psql -U <role> -d <db>"` on Linux (trust auth inside container); direct psql reading `~/.gbrain/config.json` on macOS. Roles connect WITHOUT passwords inside the container; direct TCP to :15432 from the host requires a password (pg_hba scram for non-localhost).

## Schema Gotchas (found by real CLI testing 2026-08-02 — all fixed in mycortex.sql)

1. **`mycortex_reader` needs `search_config` column grant.** Original grant was
   `SELECT (id, name, is_federated)` on sources — the search query joins sources
   for per-source FTS config and fails `permission denied for table sources`.
   Fix: `GRANT SELECT (id, name, is_federated, search_config) ON mycortex.sources`.
2. **FORCE RLS default-denies mycortex_admin.** With FORCE RLS and no admin
   policy, admin sees ZERO rows from pages/content_chunks — stats/audit queries
   silently return 0. Fix: add `mycortex_pages_admin` / `mycortex_chunks_admin`
   `FOR SELECT TO mycortex_admin USING (true)` policies. Admin = audit role.
3. **`sources.host` DEFAULT is 'localhost'** (not `current_setting('hostname',...)` — that GUC returns NULL and violates NOT NULL). CLI passes the real host explicitly.
4. **Chunks RLS does NOT rely on page-RLS cascade** — policy subqueries evaluate as the table owner (superuser, bypasses RLS), so the chunks policy independently applies the same federated/grant predicate.

## Testing

- `bash tests/test-mycortex-schema.sh` — S-003 AC battery (15 checks) on scratch
  DB `mycortex_test`; hermeticity guard refuses `gbrain` DB.
- End-to-end CLI test on a scratch DB: `CREATE DATABASE mycortex_test` → `migrate.py --db-name mycortex_test` → add source (local mode) → sync → search → verify isolation (reader sees ZERO rows from isolated source, even with `--source`; grant → reader sees it).
- **Never test against the prod `gbrain` DB** — always `--db-name mycortex_test`.

## Migration Status (2026-08-02, session completed the deploy)

- ✅ S-001 golden parity harness, S-003 schema v001 (deployed, 15/15 tests green)
- ✅ CLI built (sources/sync/search/list/stats/doctor), verified end-to-end on scratch DB
- ✅ `import-gbrain.py` (one-shot additive gbrain→mycortex copy, idempotent, dry-run, --federated with PII gate) — registered in cortex-update.sh
- ✅ Prod import on esther: 642 pages / 3582 chunks migrated, `hermes-cortex` + `default` federated (PII gate recorded) — run via `python3 ~/.hermes-cortex/services/mycortex/import-gbrain.py --federated hermes-cortex --federated default`
- ✅ Cron `agent-mycortex-sync` (S-009) — every 15 min, per-host (NOT orchestrator-only, design D4), no_agent wrapper, registered in `install-crons.sh` (both arrays)
- ✅ Sync performance: batched VALUES-join SQL — 1552 files in ~3s (design target 1500/30s)
- ⏳ Remaining: parity gate (S-010), gbrain decommission (S-011..S-016)

See `references/migration-2026-08-02.md` for the full session trace: schema fixes, CLI verification outputs, and what remains.

## Pitfalls

- **`mycortex search` as reader returns `[]` for isolated sources by design** — RLS fail-closed. Don't "fix" it by running search as admin; grant the reader (`source_grants`) or federate with a PII scan.
- **`--source` filter does NOT grant access** — RLS is the enforcement, the filter is only a filter.
- **Sync writes are per-statement psql autocommits** — the sync loop is not one big txn; a crash mid-sync leaves partial upserts (acceptable: re-sync is idempotent by content_hash).
- **git mode uses `git ls-files --cached --others --exclude-standard`** — excludes .git internals and honors .gitignore.
- **macOS migrate.py needs `-t -A`** in `_psql_base` — missing it makes `current_version()` parse the `coalesce` column header as a version (fixed 2026-08-02 by Titus).
- **gbrain slugs ≠ mycortex relpaths — import must map, not copy.** gbrain stores `slug` relpaths (extension-stripped + lowercased: `skills/.../skill` for `SKILL.md`, `docs/agent-architecture` for `.md`). mycortex's canonical relpath is the REAL file path (golden queries assert `.md`/`SKILL.md`). Copying slugs verbatim makes the first sync's mass-deletion guardrail fire (every imported page looks "missing" → 642/642 abort). import-gbrain.py walks each source tree, builds slug→real map, inserts with real paths, and prunes slug-path dupes — fully idempotent across re-runs.
- **A post-pass relpath rewrite breaks import idempotency.** If the transform (slug→real) happens AFTER insert, re-running the import inserts fresh slug rows that no longer conflict with the already-renamed rows → duplicates (observed: 642 pages became 1279 after 2 runs). The mapping must live IN the INSERT (ON CONFLICT on the real path) plus a prune step, so re-runs upsert the same rows.
- **Per-row psql through `sg docker` is ~1s/call — batch with VALUES joins.** The original sync loop did 4 psql calls per page (~10s/page → hours for 1600 files). Batched to 5 calls per source total (page upsert, id lookup, chunk delete, chunk insert, FTS rebuild) using `INSERT ... VALUES (...),(...)` and `UPDATE ... FROM (VALUES ...) AS v(...)` — 1552 files in ~3s. Any tool that shells out to psql per row (sync, import, migration) must batch; also remember `::uuid` casts when joining VALUES text against uuid FK columns.
- **Empty local_path sources are builtin placeholders — mark them synced.** `sync` skips sources with empty local_path (e.g. builtin `default`); if the skip branch doesn't update `last_sync_at`, `mycortex doctor` flags them stale forever. Update the cursor on skip.

## Related

- `gbrain-maintenance` — the old system's lifecycle (autopilot, dream, PGLite); decommission target.
- `cortex-deployment-sync` — pull/update/deploy cycle that ships mycortex files.
