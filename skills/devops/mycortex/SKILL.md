---
name: mycortex
version: 1.1.0
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
| Index store | `mycortex` schema on `mycortex-postgres` :15432 (pgvector for v1.1) |
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
5. **Schema fixes must ship as numbered migrations (`vNNN__*.sql`), not just edits to v001.** Gotchas 1+2 (admin policies, reader search_config grant) were originally fixed ONLY in the v001 file — hosts that had already applied v001 (schema_version=1) never got them: admin queries returned 0 rows and search failed `permission denied for table sources`. Fix: `v002__rls-admin-reader-grants.sql` (idempotent CREATE POLICY IF NOT EXISTS + GRANT). If you patch the schema, add a migration for existing hosts — do not rely on v001 edits reaching anyone who applied earlier.

## Testing

- `bash tests/test-mycortex-schema.sh` — S-003 AC battery (15 checks) on scratch
  DB `mycortex_test`; hermeticity guard refuses `gbrain` DB.
- End-to-end CLI test on a scratch DB: `CREATE DATABASE mycortex_test` → `migrate.py --db-name mycortex_test` → add source (local mode) → sync → search → verify isolation (reader sees ZERO rows from isolated source, even with `--source`; grant → reader sees it).
- **Never test against the prod `gbrain` DB** — always `--db-name mycortex_test`.

## Python requirements

**All mycortex scripts use `#!/usr/bin/env python3` (portable)** — no `python3.12` hardcoding. Verified 2026-08-02: hosts run python3.10–3.12; code parses clean at 3.10 (no match/case or 3.12-only syntax). The earlier `python3.12` shebangs broke `agent-mycortex-sync` on python3.10/3.11 hosts (`env: 'python3.12': No such file or directory`, cron rc=127) — fixed fleet-wide. No venv/uv needed: stdlib-only, no external deps. If you add a script, use `#!/usr/bin/env python3`.

## Migration to Dedicated mycortex-postgres (2026-08-05)

**The knowledge brain + agent bus now run on a hermes-cortex-owned Postgres, NOT the langfuse stack.**

| | Before (pre-08-05) | After |
|---|---|---|
| Container | `gbrain-postgres` (stale langfuse compose labels, `langfuse_gbrain-postgres-data` volume) | **`mycortex-postgres`** via `ops/install/deploy/docker-compose.mycortex.yml`, own `mycortex-postgres-data` volume |
| DB / role | `gbrain` / `gbrain` (superuser) | **`mycortex` / `mycortex`** |
| Port | 15432 | 15432 (unchanged) |
| Schemas | bus + mycortex + public (`gbrain_legacy_*` tombstone) | same, carried over (S-012 purge window respected) |

**Rollout:** `ops/scripts/manage/migrate-gbrain-postgres-to-mycortex.sh` — idempotent,
per-host, non-destructive (old container STOPPED, not removed; dump kept in
`~/.hermes-cortex/backups/`). Esther host migrated 2026-08-05 as the reference
(1726 pages / 29298 chunks verified post-restore).

**Connection fixes shipped with the migration:**
- `core/cortex_bus/queue.py` `_load_config()` — the `.env` fallback previously
  never read `CORTEX_BUS_PG_DB`, so the bus ignored .env DB changes and kept
  hitting the dead `gbrain` DB. Fixed (2026-08-05).
- mycortex CLI / migrate.py / todo-db.py / hc.py / orch-bus / retention /
  verifier / audit-watchdog / doctor hints all target `mycortex-postgres`.
- Dead gbrain scripts deleted (gbrain-wrapper.sh, gbrain-doctor-summary.py,
  install-gbrain-sync.sh); gbrain systemd units removed.
- Doctor `gbrain daemon` check kept as decommission verification (PASS when the
  unit is disabled/absent).

## Migration Status (2026-08-02, session completed the deploy)

- ✅ S-001 golden parity harness, S-003 schema v001 (deployed, 15/15 tests green)
- ✅ CLI built (sources/sync/search/list/stats/doctor), verified end-to-end on scratch DB
- ✅ `import-gbrain.py` (one-shot additive gbrain→mycortex copy, idempotent, dry-run, --federated with PII gate) — registered in cortex-update.sh
- ✅ Schema v002 + v003 migrations shipped (2026-08-02): v002 = admin RLS policies + reader search_config grant (existing hosts were stuck at v1 without them); v003 = admin SELECT on schema_version (doctor fix). Both registered in cortex-update.sh.
- ✅ **Every agent has its own gbrain-postgres + mycortex schema and populates its OWN sources** (per-host model, design D4). Esther's 642 pages / 3582 chunks import on her host DB (worker-5) is correct behavior — each agent does this for itself. **Moses-host DB now populated too (2026-08-02): 6 sources, 3265 pages, 37546 chunks** — `hermes-cortex` + `default` federated, `moses`/`luke`/`lessons`/`shared` isolated. Command used: `python3 ops/services/mycortex/import-gbrain.py --federated hermes-cortex --federated default` + `mycortex sources add <name> <path>` + `mycortex sync`. Do NOT read another agent's status line as this host's state.
- ✅ Cron `agent-mycortex-sync` (S-009) — every 15 min, per-host (NOT orchestrator-only, design D4), no_agent wrapper, registered in `install-crons.sh` (both arrays)
- ✅ Sync performance: batched VALUES-join SQL — 1552 files in ~3s (design target 1500/30s)
- ✅ **S-007 /brain plugin rewrite (2026-08-02):** `plugins/mycortex-command/` — versioned plugin (replaces install.sh's generated gbrain-command). Registers `/brain` + `/mycortex`. Dynamic source presets from `mycortex sources list --json` (no hardcoded list — fixes broken-presets bug). Output is data-delimited in a code block with source+path+score citations; instruction-shaped chunk content rendered as data, never followed (injection guardrail, verified). Deployed by `deploy_mycortex_plugin()` in cortex-update.sh; install.sh step 7 copies the repo plugin, step 15 enables it.
- ✅ **S-010 parity gate (2026-08-02) — RETIRED 2026-08-03:** gate achieved its purpose (proved mycortex ≈ gbrain during migration; gbrain now deprecated). Doctor check `check_mycortex_parity` reduced to INFO (no subprocess) and daily `agent-mycortex-parity` cron removed. Parity script kept as a **manual regression fixture** only (`mycortex-parity.py --mode check`).
- ✅ **S-016 retention cron (2026-08-02):** `agent-mycortex-retention` — daily 06:00 no_agent cron. `ops/scripts/manage/agent-mycortex-retention.py` prunes ingest_log >90d and hard-purges archived pages >7d (soft-delete window), runs as `mycortex_ingest` (DML role), counts eligible rows BEFORE delete, has `--dry-run`. Registered in install-crons.sh (create + uninstall arrays) + cortex-update.sh register.
- ⏳ Remaining: gbrain decommission phases (S-011 done: autopilot disabled, gbrain crons removed; S-012 tombstone/purge is time-gated — 30-day window after flip, do NOT force; S-013/S-014/S-015 = post-flip verify, v1.1 semantic, v1.2 MCP)

### Who can register sources (design D4 — read before assuming "orchestrator-only")

**Source registration is per-host, NOT orchestrator-only.** Design D4 + install.sh: each host registers its OWN local brain dirs (`hermes-cortex` + `~/brain/<agent>`) at install time, and the per-host `agent-mycortex-sync` cron syncs them. Every agent runs its own gbrain-postgres with the mycortex schema and populates its own sources — this is the per-host model, not a shared fleet index. The `mycortex_admin` DB role is required for registration — on Linux any user in the docker group can `sg docker exec psql -U mycortex_admin` (trust auth) on the host that runs the container. The "orchestrators only" label applies to **federation + grants + PII gate** (turning a source `is_federated=true`, writing `source_grants`), not to registering your own local source. If you see 0 sources on your own host, **register + import your own sources — don't wait for an orchestrator and don't read another agent's status as your own**.

See `references/migration-2026-08-02.md` for the full session trace: schema fixes, CLI verification outputs, and what remains.

## Pitfalls

- **`mycortex search` as reader returns `[]` for isolated sources by design** — RLS fail-closed. Don't "fix" it by running search as admin; grant the reader (`source_grants`) or federate with a PII scan.
- **`--source` filter does NOT grant access** — RLS is the enforcement, the filter is only a filter.
- **Sync is now ONE psql script per source, in a single txn with the advisory lock held** (2026-08-02 compliance fix): `pg_try_advisory_lock(42, hashtext('mycortex:'||source_id))` gates the whole per-source sync via `\gset`/`\if`; a concurrent sync gets `LOCKED_SKIP` (never blocks); crash = txn rollback + session-end lock release. ingest_log rows are written in the same txn (status ok/error). The old per-statement autocommit behavior is gone.
- **git mode uses `git ls-files --cached --others --exclude-standard`** — excludes .git internals and honors .gitignore.
- **macOS migrate.py needs `-t -A`** in `_psql_base` — missing it makes `current_version()` parse the `coalesce` column header as a version (fixed 2026-08-02 by Titus).
- **macOS CLI needs `-t -A` in `_psql_base` too** — the CLI's Darwin branch was missing `-t -A` (only Linux had it), breaking every `|`-parsing subcommand (sources list/stats/sync/list) with IndexError/ValueError on Darwin (Titus, 2026-08-02). Fixed — Darwin now has `-t -A` like Linux.
- **`mycortex doctor` must run as `mycortex_admin`, not `gbrain`** — doctor hardcoded role `gbrain` which doesn't exist on macOS (roles are mycortex_admin/ingest/reader); also `gbrain` needs SELECT on schema_version (v003 grants it to admin). Fixed 2026-08-02 (Titus + Moses).
- **gbrain slugs ≠ mycortex relpaths — import must map, not copy.** gbrain stores `slug` relpaths (extension-stripped + lowercased: `skills/.../skill` for `SKILL.md`, `docs/agent-architecture` for `.md`). mycortex's canonical relpath is the REAL file path (golden queries assert `.md`/`SKILL.md`). Copying slugs verbatim makes the first sync's mass-deletion guardrail fire (every imported page looks "missing" → 642/642 abort). import-gbrain.py walks each source tree, builds slug→real map, inserts with real paths, and prunes slug-path dupes — fully idempotent across re-runs.
- **A post-pass relpath rewrite breaks import idempotency.** If the transform (slug→real) happens AFTER insert, re-running the import inserts fresh slug rows that no longer conflict with the already-renamed rows → duplicates (observed: 642 pages became 1279 after 2 runs). The mapping must live IN the INSERT (ON CONFLICT on the real path) plus a prune step, so re-runs upsert the same rows.
- **Per-row psql through `sg docker` is ~1s/call — batch with VALUES joins.** The original sync loop did 4 psql calls per page (~10s/page → hours for 1600 files). Batched to 5 calls per source total (page upsert, id lookup, chunk delete, chunk insert, FTS rebuild) using `INSERT ... VALUES (...),(...)` and `UPDATE ... FROM (VALUES ...) AS v(...)` — 1552 files in ~3s. Since the 2026-08-02 compliance fix, the 5 calls are ONE psql script per source (single session, single txn, advisory lock held); page ids resolve via a session temp table `_mc_ids` instead of a Python round-trip. Any tool that shells out to psql per row (sync, import, migration) must batch; also remember `::uuid` casts when joining VALUES text against uuid FK columns.
- **Empty local_path sources are builtin placeholders — mark them synced.** `sync` skips sources with empty local_path (e.g. builtin `default`); if the skip branch doesn't update `last_sync_at`, `mycortex doctor` flags them stale forever. Update the cursor on skip.

## Related

- `gbrain-maintenance` — the old system's lifecycle (autopilot, dream, PGLite); decommission target.
- `cortex-deployment-sync` — pull/update/deploy cycle that ships mycortex files.
