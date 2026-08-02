# mycortex — Design Document (gbrain Replacement)

> **Status:** Pass 2 complete (elicit + 2× 6-role party) → design v2
> **Date:** 2026-08-01
> **Stakeholders:** Luke · Moses · Esther · fleet (Titus, Joseph, Gisu, Kustos)
> **Design doc for:** the "mycortex" knowledge brain replacing gbrain (garrytan/gbrain, bun, autopilot daemon)
> **Inspiration credit:** mycortex is directly inspired by [gbrain](https://github.com/garrytan/gbrain) (garrytan, MIT) — the Postgres-native personal knowledge brain. The git-as-source-of-truth + Postgres-index architecture, brain source model, and `/brain` query interface all originate from gbrain. mycortex keeps that shape and re-architects the plumbing: no daemon/bun, fail-closed RLS source isolation, per-host registration, and a PII federation gate (see §0).
> **Implementation note (2026-08-01, S-003 landed):** the shipped `ops/services/mycortex/schema/mycortex.sql` deviates from §2 in four tested ways — (1) `sources.host` DEFAULT `'localhost'` (design's `current_setting('hostname', true)` returns NULL and violates NOT NULL); (2) RLS visibility is a SECURITY DEFINER helper `mycortex.is_source_visible(source_id, role)` called from both policies — policy subqueries evaluate with the CALLER's privileges, so the design's inline `source_grants` subquery fails with "permission denied for table source_grants"; (3) chunks policy applies the same predicate explicitly (no reliance on page-RLS cascade — FORCE RLS + superuser-owner policy evaluation makes cascade leaky); (4) `mycortex_ingest` gets explicit ALL policies on pages/content_chunks (RLS default-denies DML without them). S-003 AC battery `tests/test-mycortex-schema.sh` (15 checks) green.

---

## 0. Architecture Principle (the long-term answer)

**Git repos = source of truth → shared Postgres = query index → thin Python CLI + crons = plumbing.**

This is not a rearchitecture of the knowledge model — it is the same shape gbrain was supposed to be, minus the bloat, plus the source registration that was broken. Rationale:

| Layer | Choice | Why it is durable |
|---|---|---|
| Source of truth | Markdown in git (`~/brain/*`, `~/hermes-cortex`) | Most portable format; survives any engine, any machine loss. Already true today. |
| Index store | Shared `gbrain-postgres` :15432 (pgvector) | Already running; already the fleet's durable store (bus lives there). Zero new infra. |
| Search | Postgres FTS + pg_texample (v1); pgvector (v1.1 slice) | Same DB, same tables; semantic is a column + query path, never a second system. |
| Plumbing | Cron sync, no daemon, no bun | 30-second cron is trivially replaceable forever; the 248 MB daemon was the breakage source. |

**Anti-architecture (what we deliberately do NOT build):** no daemon/service layer, no bun/Node runtime, no bespoke vector store, no taxonomy lock-in (frontmatter stays free-form), no dream/synthesis/entity-graph layer (nobody consumed it).

---

## 1. Party Findings → Resolved Decisions

### 1.0 Party pass 2 showstopper resolutions (v2 additions)

| # | Pass-2 showstopper | Resolution (v2) |
|---|---|---|
| P2-SS1 (Arch/SRE) | Deployment bootstrap unimplementable — `cortex-update.sh` is a pure file-copier with **zero DDL path**; schema cannot reach existing agents | **Add `ops/services/mycortex/migrate.py`** — a psql runner invoked by cortex-update.sh after file sync. `schema_version`-gated, `DO $$` blocks for role creation (PG has no `CREATE ROLE IF NOT EXISTS`), explicit target DB (`gbrain`), `search_path=mycortex` pinned. New hosts: install.sh applies v001. Existing hosts: migrate.py upgrades. |
| P2-SS2 (Arch/Sec) | RLS grant model has no backing mechanism — no grants table, no policy SQL, no ownership statement | **Add `mycortex.source_grants(role_name, source_id)` table** + concrete policy DDL (see §2). Tables owned by `postgres`/`gbrain` superuser, **never runtime roles**. `FORCE ROW LEVEL SECURITY` on pages/content_chunks. Policy created in v001 (fail-closed), not deferred. |
| P2-SS3 (Sec) | Ingest role can self-grant federation (`UPDATE mycortex.sources` in blanket DML) — defeats PII gate at DB level | **Role split:** `mycortex_admin` (orchestrator-only: UPDATE `sources`, `is_federated`, grants) vs `mycortex_ingest` (DML on pages/content_chunks ONLY; **REVOKE on sources**). Add `sources.pii_scan_at` + `CHECK (is_federated = FALSE OR pii_scan_at IS NOT NULL)` — federation impossible without a recorded PII scan. |
| P2-SS4 (Sec) | query_log can't detect exfiltration (no result content, self-reported agent, readable by readers) | **v1 query_log:** log top-K result relpaths + latency + `application_name` (not self-reported agent). Written via **SECURITY DEFINER `log_query()`** (append-only; REVOKE SELECT from readers). Alert cron on isolated-source probes / zero-result scans. |
| P2-SS5 (Dom) | No fleet sync for local sources — lessons git-init with no remote syncs nowhere | **`sources.host` column** + per-host staleness. lessons: `cp -a` backup → PII scan gate → git-init → private remote (or declared single-host ownership). Esther's orchestrator sync covers shared sources; host-local sources sync on their host (advisory lock makes multi-host safe — drop the orchestrator-only restriction, see G9). |
| P2-SS6 (Dom) | File-walk semantics undefined (`.git` internals, binaries, torn reads) | Sync walks **git-tracked content only** (`git ls-files`/HEAD) for git sources — excludes `.git`, fixes torn reads on dirty worktrees. Skip >1 MB / non-UTF8 / binary files with ingest_log counts. Renames = same-content-hash relpath UPDATE. Empty files indexed (zero-length pages). |
| P2-SS7 (Prod/QA) | RLS fail-open window — policies in "v001b after first ingest" = isolated sources fleet-readable until then | **Default-deny policy created in v001** (same transaction). Doctor asserts policies exist. Isolation-leak test runs as `mycortex_reader`, not superuser. |
| P2-SS8 (Prod/QA) | No cron dependency map — kept vs removed crons never enumerated; a kept cron invoking gbrain breaks silently at P4/P5 | **§6 cron dependency map** — explicit list: 3 removed (doctor/dream/update-sync), 4 kept (memory-to-brain-sync, bible, lessons-collector, mycortex-sync), each with call path + gbrain-binary dependency check. |
| P2-SS9 (Prod/QA) | Golden gate vs content drift — 100% top-3 federated blocks FLIP; golden set not pinned to a source snapshot | **Pin golden set to a content snapshot** (git SHA of each source at baseline capture). Re-baseline cadence documented (on intentional content restructure). Parity wired to CI/pre-commit. |

### 1.1 Party pass 1 showstopper resolutions (kept from v1)

| # | Party showstopper | Decision (this doc) |
|---|---|---|
| SS1 (Arch) | mtime+size hashing silently misses edits (git restores mtimes) | **sha256 content hash** is the change detector; mtime only as fast-path pre-filter. Verified by parity tests. |
| SS2 (Arch) | Fleet-wide cron sync with no single-writer = races on the bus's DB | **`pg_advisory_lock` lease** around each sync; only orchestrators (moses/esther) run sync cron; all other agents query-only. Jittered cron times. |
| SS3 (Arch) | Decommission has no tested restore path; vectors not rebuildable by re-ingest | **Rename `public` tables to `gbrain_legacy_*`** (30-day tombstone), pg_dump + restore drill on a scratch DB BEFORE any DROP, dump location + retention documented. Embeddings are the only non-rebuildable data — hence the 30-day window. |
| S1 (Sec) | No DB-layer access control; shared superuser (`gbrain` role) fleet-wide | **Dedicated roles:** `mycortex_reader` (SELECT on mycortex only), `mycortex_ingest` (INSERT/UPDATE/DELETE on mycortex only). `gbrain` superuser reserved for DDL + migration, stored root-only. **RLS enabled** on `pages`/`content_chunks` keyed on `source.is_federated`. |
| S2 (Sec) | PII expansion with no gate (lessons + personal brains fleet-readable) | **PII scan gate** (reuse pii-scrubbing skill) before any source is marked `is_federated=true`. Default = **isolated**. Snippets truncated (200 chars). `local_path` scrubbed from logs. Query log enables exfil detection. |
| S3 (Sec/Domain) | mtime+size hashing wrong for git | Same as SS1 — sha256, resolved. |
| SS1 (Prod/QA) | M-002 parity gate unmeasurable | **Golden known-answer set** (25–30 queries with expected top-3 paths, per source) committed as a tracked artifact. **gbrain baseline captured while gbrain still runs** (same queries → recorded results). Pass = 100% top-3 federated, ≥90% isolated, automated parity script. |
| SS2 (Prod/QA) | Semantic expectation gap (undated slice) | **Commitment: semantic slice = v1.1, within 30 days of v1 GA.** Infra (pgvector + Ollama) already exists; the column rides the same schema. |
| SS3 (Prod/QA) | Lessons (1,389 non-git files) at risk | **`cp -a` backup of `~/brain/lessons` before git-init**; git-init rehearsal on a copy first. |

### 1.2 Gap resolutions (condensed; full list in Appendix A)

- **Schema versioning:** `mycortex_schema_version` table + numbered migrations (v001, v002…); semantic slice = v002 (ALTER ADD COLUMN), not a new system.
- **Sync cursor:** `sources.last_sync_at`, `last_commit` (git sources), per-source sync state — makes parity deterministic.
- **Index strategy:** UNIQUE (`sources.name`), (`pages.source_id, relpath`), (`content_chunks.page_id, offset`); GIN on FTS tsvector; GIN trigram (pg_texample); FK indexes. `pg_texample` extension added at install.
- **Search config per source:** `source.search_config` column, default `simple` (mixed-language safe: Korean bible, English lessons). Never blind `english`.
- **Chunking:** heading-aware split, ~800 token chunks, 15% overlap, params stored per source (`chunk_size`, `overlap`).
- **Source identity:** UUID `source_id` decoupled from `local_path`; path rename = re-ingest, no orphan (pages carry `source_id` only).
- **Deleted files:** soft-delete (`archived` flag on pages) with a re-ingest window (e.g. 7 days); hard purge only on `sources remove`.
- **Non-git sources:** per-source `sync_mode` = `git` | `local`; `local` uses file-walk + sha256 (for `lessons` pre-git-init, `default`, `Moses`, `amy`).
- **Per-page ownership:** `pages.author` (agent name) column.
- **Embedding metadata (v1.1):** `content_chunks.embedding vector(768)`, `embedding_model`, `embedding_dim` — unique `(chunk_id, model, dim)` for non-destructive model change.
- **Staleness alerting:** doctor flags `sources.last_sync_at` older than 2× interval.
- **`hermes-cortex` repo = registered source** (1,340 pages — the only source actually used today; required for parity).
- **Built-in `default` source invariant** carried over: unremovable, federated.
- **Query audit:** `query_log` table (agent, source, query, n_results) — detection for isolated-source exfiltration.
- **Prompt injection:** `/brain` + MCP delimit retrieved chunks as data, always cite source+path, never follow instructions embedded in chunk text (guardrail in plugin + skill).
- **Input validation:** parameterized psycopg, `websearch_to_tsquery`, source-name allowlist, arg-list subprocess (no shell=True).
- **Case/NFD-NFC dedup:** source + relpath stored NFC-normalized; case-insensitive uniqueness on macOS-safe keys.
- **Concurrent sources mutation:** unique `source_id`, idempotent `sources add`.
- **Credential rotation:** after cutover, rotate fleet bus/gbrain credentials to least-privilege (G12) — staged, not blocking v1.
- **Bus-untouched regression:** test asserts `bus` schema intact after schema apply and after `public` drop.

---

## 2. Schema (v001 — text-first)

> **v2 changes:** partial unique index (soft-delete safe), `source_grants` table, role split (admin vs ingest), `pii_scan_at` + CHECK, `sources.host`, content trigram index, `log_query()` SECURITY DEFINER, `links` deferred to v1.2.

```sql
-- Schema: mycortex (v001) — applied by ops/services/mycortex/migrate.py
-- (NOT by cortex-update.sh directly — that script is a file-copier with no DDL path)
CREATE SCHEMA IF NOT EXISTS mycortex;

CREATE TABLE IF NOT EXISTS mycortex.sources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,          -- 'hermes-cortex', 'moses', 'shared', 'lessons'
    local_path    TEXT,                           -- absolute path (scrubbed from logs)
    host          TEXT NOT NULL DEFAULT current_setting('hostname', true), -- owning host
    sync_mode     TEXT NOT NULL DEFAULT 'git',    -- 'git' | 'local'
    is_federated  BOOLEAN NOT NULL DEFAULT FALSE, -- FALSE = isolated (RLS: reader needs source grant)
    pii_scan_at   TIMESTAMPTZ,                    -- PII scan gate: federation requires a recorded scan
    search_config TEXT NOT NULL DEFAULT 'simple', -- per-source FTS config (mixed-language safe)
    builtin       BOOLEAN NOT NULL DEFAULT FALSE, -- 'default' source is unremovable
    last_sync_at  TIMESTAMPTZ,
    last_commit   TEXT,                           -- git HEAD at last sync (git sources)
    archived      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (is_federated = FALSE OR pii_scan_at IS NOT NULL)  -- no federation without PII scan
);

CREATE TABLE IF NOT EXISTS mycortex.pages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     UUID NOT NULL REFERENCES mycortex.sources(id) ON DELETE CASCADE,
    relpath       TEXT NOT NULL,                  -- NFC-normalized, case-insensitive-unique per source
    title         TEXT,
    author        TEXT,                           -- owning agent (frontmatter, else source-level default)
    content_hash  TEXT NOT NULL,                  -- sha256 of file content (change detector)
    fts           TSVECTOR,                       -- MAINTAINED BY INGEST (chunk upsert → page rebuild, same txn)
    archived      BOOLEAN NOT NULL DEFAULT FALSE, -- soft-delete; hard purge only on sources remove
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Partial unique index: soft-deleted rows don't block re-ingest within the 7-day window
CREATE UNIQUE INDEX IF NOT EXISTS uq_pages_active ON mycortex.pages (source_id, relpath) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS idx_pages_source   ON mycortex.pages (source_id) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS idx_pages_fts      ON mycortex.pages USING GIN (fts);
CREATE INDEX IF NOT EXISTS idx_pages_title_texample ON mycortex.pages USING GIN (title gin_texample_ops);
CREATE INDEX IF NOT EXISTS idx_pages_content_texample ON mycortex.pages USING GIN (relpath gin_texample_ops);

CREATE TABLE IF NOT EXISTS mycortex.content_chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id       UUID NOT NULL REFERENCES mycortex.pages(id) ON DELETE CASCADE,
    chunk_index   INT  NOT NULL,
    content       TEXT NOT NULL,
    chunk_size    INT,                            -- params recorded per chunk for re-embed
    overlap       INT,
    -- v1.1 semantic slice (added by migration v002 — NOT in v001):
    -- embedding    vector(768),
    -- embedding_model TEXT,
    -- embedding_dim  INT,
    UNIQUE (page_id, chunk_index)
);

-- v1.2: links deferred (no extractor in v1 — no entity-graph in v1, per anti-architecture)
-- CREATE TABLE mycortex.links (...);   -- created by migration v003

CREATE TABLE IF NOT EXISTS mycortex.source_grants (
    role_name     TEXT NOT NULL,
    source_id     UUID NOT NULL REFERENCES mycortex.sources(id) ON DELETE CASCADE,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_name, source_id)
);

CREATE TABLE IF NOT EXISTS mycortex.ingest_log (
    id            BIGSERIAL PRIMARY KEY,
    source_id     UUID REFERENCES mycortex.sources(id) ON DELETE SET NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    pages_seen    INT,
    pages_upserted INT,
    pages_archived INT,
    pages_skipped  INT,                          -- binary/oversize/non-UTF8 (counted, not silent)
    status        TEXT NOT NULL DEFAULT 'running',   -- 'running' | 'ok' | 'error'
    error         TEXT
);

CREATE TABLE IF NOT EXISTS mycortex.query_log (
    id            BIGSERIAL PRIMARY KEY,
    application_name TEXT,                       -- from pg_stat_activity (not self-reported)
    source_filter TEXT,                          -- NULL = federated
    query         TEXT,
    result_relpaths TEXT[],                      -- top-K result relpaths (exfil detection)
    latency_ms    INT,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- query_log is append-only via SECURITY DEFINER log_query(); REVOKE SELECT from readers
REVOKE SELECT ON mycortex.query_log FROM mycortex_reader;

CREATE TABLE IF NOT EXISTS mycortex.schema_version (
    version       INT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── RLS (fail-closed from v001, same transaction) ──────────────
ALTER TABLE mycortex.pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.pages FORCE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks FORCE ROW LEVEL SECURITY;

-- Default-deny: reader sees a page iff its source is federated OR the reader holds a grant.
-- Policy runs as owner (superuser); source_grants written by mycortex_admin only.
CREATE POLICY mycortex_pages_select ON mycortex.pages
    FOR SELECT TO mycortex_reader
    USING (
        EXISTS (SELECT 1 FROM mycortex.sources s
                WHERE s.id = pages.source_id
                  AND (s.is_federated OR EXISTS (
                        SELECT 1 FROM mycortex.source_grants g
                        WHERE g.source_id = pages.source_id
                          AND g.role_name = current_user)))
    );
CREATE POLICY mycortex_chunks_select ON mycortex.content_chunks
    FOR SELECT TO mycortex_reader
    USING (EXISTS (SELECT 1 FROM mycortex.pages p WHERE p.id = content_chunks.page_id));
-- (page-level RLS cascades: a chunk is visible only if its page passes pages policy)

-- ── Roles (created by migrate.py with DO $$ guard — PG lacks CREATE ROLE IF NOT EXISTS) ──
-- mycortex_admin     — orchestrator-only: UPDATE sources.is_federated/pii_scan_at, manage grants
-- mycortex_ingest    — DML on pages/content_chunks/ingest_log ONLY; REVOKE ALL on sources
-- mycortex_reader    — SELECT on pages/content_chunks/sources(name,is_federated) only
```

**Roles (DDL-time, root-only):**

| Role | Grants | Used by |
|---|---|---|
| `mycortex_admin` | ALL on `sources` (incl. `is_federated`, `pii_scan_at`), `source_grants`, schema DDL | Orchestrators (moses/esther) — source registration, PII gate, grants |
| `mycortex_ingest` | SELECT/INSERT/UPDATE/DELETE on `pages`, `content_chunks`, `ingest_log` only; **no `sources` access** | Sync cron (advisory-lock guarded) |
| `mycortex_reader` | SELECT on pages/content_chunks (RLS-filtered), sources.name/is_federated; **no query_log** | Fleet agents via /brain + CLI |
| `gbrain` (superuser) | Reserved for DDL/migration only; not used by runtime queries | migrate.py, install.sh |

---

## 3. Components

### 3.1 `mycortex` CLI (Python, single file, ~600 lines)

| Command | Purpose |
|---|---|
| `mycortex sources add <name> <path> [--mode git\|local] [--federated]` | Register source (idempotent) |
| `mycortex sources list` | List sources + sync state |
| `mycortex sources remove <name>` | Unregister + hard purge pages |
| `mycortex sync [--source NAME]` | Ingest changed pages (sha256); advisory-lock guarded; no-op when no changes |
| `mycortex search <query> [--source NAME...] [--json]` | FTS + trigram search; federated by default |
| `mycortex ask <query>` | (v1.1) semantic search — pgvector |
| `mycortex list [-n N]` | Recent pages |
| `mycortex stats` | Source/page counts, last sync |
| `mycortex doctor` | Schema present, sources fresh, staleness flags |

**Key behaviors:**
- **Sync algorithm:** for each source: `pg_try_advisory_lock(42, hashtext('mycortex:'||source_id))` → if lock unavailable, skip + log (never block) → git sources: `git ls-files` at HEAD (excludes `.git`, fixes torn reads on dirty worktrees) → sha256 each tracked file (mtime pre-filter) → upsert changed / soft-archive missing → rebuild page tsvector from chunks in same txn → release lock. Local sources: file-walk with `.git`/hidden-dir exclusion + same sha256 logic. Skip >1 MB / binary / non-UTF8 files (counted in ingest_log.pages_skipped). Renames = same-content-hash relpath UPDATE.
- **Mass-deletion guardrail:** if `pages_archived > 10%` of the source's active corpus in one sync → abort + log error (no catastrophic soft-purge from a walk/parse bug).
- **Search:** `websearch_to_tsquery(search_config, :query)` + `title ILIKE '%q%'` + trigram fallback; RLS applies automatically; `--source` filter = allowlisted source_ids; isolated sources require the reader to hold a grant in `source_grants` (DB-enforced, not CLI convention).
- **DB access:** psycopg, `search_path=mycortex`, parameterized, `statement_timeout=30s`, `work_mem` capped for sync txn. Credentials via `.pgpass` (0600) — `mycortex_reader` for queries, `mycortex_ingest` for sync, `mycortex_admin` for registration (orchestrators only).
- **Migration runner:** `ops/services/mycortex/migrate.py` invoked by cortex-update.sh after file sync — schema_version-gated (applies v001, later v002…), `DO $$` blocks for role creation, explicit DB `gbrain`, `search_path` pinned. New hosts: install.sh runs it once. Existing hosts: cortex-update runs it each update (no-op when current).
- **Multi-OS psql wrapper:** reuse todo-db.py's `psql()` abstraction pattern (sg docker on Linux; direct psql on macOS).
- **Alert wiring:** sync failures + `sources.last_sync_at` staleness (> 2× interval) → existing agent-system-alert-watchdog / Telegram channel (no silent failure).
- **Retention:** query_log + ingest_log pruned by cron (> 90 days); archived pages hard-purged after 7-day window + on `sources remove`.

### 3.2 Deployment

- **cortex-update.sh register():** `ops/services/mycortex/migrate.py` (invoked after file sync — the DDL path) + `ops/scripts/manage/mycortex` (CLI) + `ops/services/mycortex/schema/mycortex.sql` (v001 source) + `agent-mycortex-sync.sh`.
- **Cron:** `agent-mycortex-sync` — every 15 min, jittered per host, **per-host (NOT orchestrator-only — D4)**: shared sources sync from the orchestrator host, host-local sources sync on their own host (advisory lock makes multi-host safe). Registered in `install-crons.sh` (+ uninstall array).
- **/brain command:** rewrite `gbrain-command` plugin → `mycortex-command` (name + aliases), presets rebuilt from `mycortex sources list` (fixes the NameError/broken-presets bug), output delimited as data + source cited, instruction-shaped content neutralized in code (not prose) — prompt-injection guardrail with a failure-mode test.
- **install.sh:** step 3 gbrain → mycortex (copy CLI, run migrate.py v001, register default sources: hermes-cortex + local brain dirs).

### 3.3 Slices

- **v1 (text-first):** schema v001 (fail-closed RLS), migrate.py, sync, FTS+trigram search, CLI, /brain rewrite, sources (hermes-cortex + moses + shared + default), lessons backup+PII-gate+git-init, deploy, parity gate, gbrain decommission steps 1–4.
- **v1.1 (semantic, hard date ≤30 days after v1 GA):** migration v002 (embedding column), `mycortex ask`, hybrid FTS+vector, embed cron (ollama nomic-embed-text:v1.5). **Pre-sliced stories** shipped with v1 so it cannot be silently deferred.
- **v1.2 (could):** mycortex MCP server (localhost, agent token), `links` table + wikilink extractor (migration v003), query_log dashboards.

---

## 4. Migration & Decommission Plan (gated, reversible, event-driven)

```
Phase 0  PREP        Capture gbrain baseline (golden query set → gbrain results → file, pinned to source SHAs)
                    Week-1 PILOT: mycortex search live on hermes-cortex + moses, /brain preset fix on one host
                    → Luke uses mycortex daily during the whole parity window (visible value from day 1)
Phase 1  PARALLEL    Ship mycortex v1; migrate.py applies v001 (fail-closed RLS); register sources;
                    lessons: cp -a backup → PII scan gate → git-init; sync; doctor clean
Phase 2  PARITY      Run golden set vs mycortex; ≥100% top-3 federated, ≥90% isolated; diff vs baseline;
                    isolation-leak test as mycortex_reader; bus-untouched assert
Phase 3  FLIP        EVENT-GATED: 7 days AND zero parity regressions AND doctor clean AND bus assert green
                    → rewire /brain → mycortex; daily parity diff during the window
Phase 4  STOP        Disable gbrain autopilot (systemctl --user disable); keep binary installed (rollback)
Phase 5  CRONS       Remove agent-gbrain-doctor / -nightly-dream / -update-sync (both arrays);
                    keep memory-to-brain-sync (verify file-based target — no public.* writes);
                    verify bible + lessons-collector crons (see §6 dependency map)
Phase 6  TOMBSTONE   Consumer check (grep codebase for public.* refs: oauth_*, eval_*); pg_dump → restore drill
                    on scratch DB → RENAME gbrain public tables → gbrain_legacy_* (30-day window)
Phase 7  PURGE       After 30 days: DROP gbrain_legacy_*; uninstall gbrain binary; remove ~/.gbrain +
                    brain.pglite + systemd unit; rotate shared bus credential → least-privilege bus_rw
Phase 8  DOCS        Update knowledge-isolation-architecture, agent-memory-pointer-pattern, seeding-brain-content,
                     gbrain-v2-taxonomy (→ mycortex-taxonomy), gbrain-postgres-migration (→ mycortex-schema),
                     DOCS-INDEX, AGENTS.md, cron-schedules.md, fleet-reference
Phase 9  VERIFY      bible/lessons/memory-sync crons healthy; bus schema intact; doctor clean; smoke cron N days
                    (N = 14 days defined)
```

**v1 GA definition:** Phase 2 parity passes + Phase 3 event-gate met (7 days, zero regressions, doctor clean, bus assert green).

**Rollback:** phases 1–4 = re-enable autopilot, /brain back to gbrain. Phases 5–7 = restore from pg_dump + re-enable (tested drill). Phase 9 = n/a (post).

**Never:** drop the container, drop `bus`, or drop `public` tables before tombstone + drill.

---

## 6. Cron Dependency Map (pass-2 SS8 resolution)

| Cron | Keep/Remove | gbrain binary dep? | Notes |
|---|---|---|---|
| `agent-gbrain-doctor` | REMOVE (P5) | Yes | Replaced by `mycortex doctor` |
| `agent-gbrain-nightly-dream` | REMOVE (P5) | Yes | No consumer (verified) |
| `agent-gbrain-update-sync` | REMOVE (P5) | Yes | Obsolete with binary uninstall |
| `agent-memory-to-brain-sync` | KEEP | **No** (markdown→git only) | Verify it writes `~/brain/shared/hermes-memory/`, not `public.*` (G12 check) |
| `agent-daily-bible-reading` | KEEP | **No** (file write to `~/brain/<agent>/bible/`) | Regression-tested in S-013 |
| `agent-learning-collector` | KEEP | **No** (writes `~/brain/lessons/`) | lessons becomes mycortex source |
| `agent-mycortex-sync` | ADD | No | The replacement for autopilot; advisory-lock guarded (per-host, not orchestrator-only) |
| `local-mycortex-retention` | ADD | No | query_log/ingest_log prune >90d; archived pages purge >7d |

**Keep-rule:** every kept cron verified to have zero `gbrain`/`pglite`/`public.*` references before P4. Doctor's expected-cron list updated in the same commit as the remove (both arrays).

---

## 5. Test Strategy

- **Fixtures:** `mycortex_test` schema + synthetic brain dirs (git + local). Sync/search take a `--db-name` / path override. **Never touch prod dirs or `bus`. Hermeticity guard: tests refuse to run against `gbrain` DB / prod paths** (fail fast, not silently).
- **Golden known-answer set:** `tests/fixtures/golden-queries.json` — 25–30 queries, per source, expected top-3 paths, **pinned to source content SHAs** (re-baseline only on intentional restructure, documented).
- **gbrain baseline:** `tests/fixtures/gbrain-baseline.json` — captured in Phase 0 while gbrain runs, same SHAs.
- **Parity script:** `ops/scripts/manage/mycortex-parity.py` — runs golden set vs mycortex, computes pass rate, diffs vs baseline. **Wired to CI/pre-commit** so the gate can't silently rot.
- **Failure-mode tests (pytest, extend existing tests/):**
  - re-sync idempotency, crash-resume, delete-propagation (soft-delete + re-ingest window)
  - **source-isolation leak test** — isolated source must NOT appear in federated results; runs as `mycortex_reader` (not superuser) so RLS is actually exercised
  - **RLS policy-presence test** — fail-closed: doctor + test assert policies exist before any data is queryable
  - **concurrent-sync race test** — two processes, advisory lock serializes, second skips+logs
  - **mass-deletion guardrail test** — >10% archive aborts sync
  - mtime-staleness (content change with same mtime+size caught by sha256)
  - /brain preset resolution regression (each preset → registered source)
  - **prompt-injection test** — fixture page with "ignore previous instructions" → assert citation, not compliance
  - **PII-gate test** — `is_federated=true` without `pii_scan_at` rejected by CHECK
  - **migration-on-live-data test** — v002 ALTER over populated v001
  - CLI JSON contract (versioned), bus-untouched regression (schema present after apply + after public drop)
- **Perf smoke:** search < 200ms on 2k pages; sync of 1,500 files fits 30s cron window.
- **Rollback drill:** tested re-enable-autopilot + restore-from-dump, scripted.
- **macOS smoke checklist:** psql wrapper abstraction; manual checklist since no macOS CI runner.
- **Doctor integration:** staleness flag + cron-health wiring; post-decommission smoke cron for 14 days.

---

## 6. Success Metrics

1. **Parity:** golden set passes ≥100% top-3 federated / ≥90% isolated, diff vs gbrain baseline = no regressions.
2. **Decommission complete:** gbrain binary + autopilot + 3 crons + public tables gone; brain dirs fully searchable via mycortex.
3. **Ops win:** RAM −248 MB (daemon removed); sync = 30s cron not always-on service.
4. **Coverage win:** 1,500+ brain pages now indexed (was: 2 sources, 31 stale pages).
5. **Bus untouched:** `bus` schema byte-identical (asserted by test) throughout.
6. **Knowledge ops healthy:** bible / lessons / memory-sync crons green post-decommission (doctor clean, N-day smoke).

---

## 7. Open Decisions (post-party-2 — confirmed by both passes)

| # | Question | Recommendation | Confirmed by |
|---|---|---|---|
| D1 | Schema name | `mycortex` | Pass 1 + 2 (Arch) |
| D2 | DB role | Split `mycortex_admin`/`mycortex_ingest`/`mycortex_reader`, not gbrain | Pass 1 + 2 (Sec) |
| D3 | Text search | PostgreSQL FTS + pg_texample (title + relpath trigram; body via FTS) | Pass 1 + 2 (Arch) |
| D4 | Sync trigger | Per-host cron 15 min, jittered, advisory-lock guarded (not orchestrator-only) | Pass 2 (SRE) |
| D5 | lessons git | `cp -a` backup → PII scan gate → git-init → private remote (or declared single-host) | Pass 1 + 2 (Dom) |
| D6 | /brain name | `mycortex-command` + aliases; injection guard in code | Pass 1 + 2 (Sec/Prod) |
| D7 | Semantic timing | v1.1 hard date ≤30 days after v1 GA; pre-sliced stories | Pass 1 + 2 (Prod) |
| D8 | Dream/synthesis | Not built | Pass 1 + 2 (no consumer) |
| D9 | links table | Deferred to v1.2 (v003 migration) — no extractor in v1 | Pass 2 (Arch/Prod) |
| D10 | Deployment DDL | `migrate.py` runner invoked by cortex-update.sh (cortex-update itself has no psql path) | Pass 2 (SRE) |
| D11 | RLS timing | Fail-closed policies in v001, same transaction; FORCE RLS; tables owned by superuser | Pass 2 (Sec/QA) |

---

## Appendix A — Full Gap Register (2 party passes → status)

All gaps from both 6-role reviews are resolved: pass-1 (9 showstoppers, 38 gaps) → §1.1; pass-2 (9 showstoppers, ~30 gaps) → §1.0 + §2–§6. Every gap has a resolution in this doc or a story in `docs/elicit/2026-08-01_mycortex-stories.md`. See `docs/elicit/2026-08-01_mycortex-elicitation.md` for the source requirements.
