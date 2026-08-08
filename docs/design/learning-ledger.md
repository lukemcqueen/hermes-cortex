# Learning Ledger — Fleet Learning Capture (F-001)

**Status:** Implemented 2026-08-08 · **Party:** Option A verdict (7.65 weighted),
docs/elicit/2026-08-08_self-healing-auto-learning-party.md · **Tasks:** F-001 → F-002/F-006 wire consumers

## Problem

Eight capture routes (brain pending, brain lessons, session corrections,
governance cycles, LLM-judge, remediation, user feedback, cron outputs) write
learnings into **six+ separate stores** — brain/, skills/, SOUL.md, memory,
session DB, governance DB, mycortex. No unified ledger, no dedup across
stores, no status (evaluated? applied? verified? retired?), no impact score.
Remediation fixes in particular are lost: the fixer fixes, verifies, reports —
and the fix pattern is re-learned by the next agent (P-06).

## Design (party L-1..L-6)

One `learnings` schema on the **bus Postgres** (the mycortex-postgres that
also hosts `bus.*` — orchestrator-only, mirrored by the forwarder for
failover). All 8 routes write rows via a **single INSERT-only write path**;
orch-skill-lifecycle (F-006) is the only UPDATE path.

```
  8 capture routes (any agent, no_agent)
        │
        ▼  learning-collect.py (CLI)  →  lib.cortex_bus.learning_capture()
        │        │
        │        ▼  POST /api/learnings   (existing bus auth: Bearer | nginx Basic)
        │        │        │
        │        ▼        ▼
        │   bus server (server.py) — authenticates, validates route/type
        │        │
        │        ▼  SELECT * FROM learnings.capture(...)   ← SECURITY DEFINER,
        │        │                                          the ONLY writer
        ▼        ▼
   learnings.learning  (bus Postgres, db `mycortex`, schema `learnings`)
        │
        ▼  F-006 orch-skill-lifecycle: SELECT + learnings.set_status()
```

### Table

`learnings.learning`: id UUID, route (enum of the 8 routes), agent (from bus
auth, never client-supplied), type, content (1..4000 chars), content_hash
(sha256 of **scrubbed** content), status (pending/evaluated/applied/verified/
retired), impact_score (-3..+3), source_ref (provenance), applied_ref
(what it became — F-005), created_at/updated_at/status_changed_at.

### Party decisions baked in

| # | Decision | Implementation |
|---|----------|----------------|
| L-1 | INSERT-only collectors; lifecycle the only UPDATE path | `learnings.capture()` SECURITY DEFINER is the only writer; NO table DML grants to any non-owner role. `learnings.set_status()` gates status transitions. Collectors never touch Postgres — they POST via the bus API. |
| L-2 | Scrub hook strips PII at insert | BEFORE INSERT trigger `scrub_content()`: email → `user@client-domain.com`, IPv4 → `x.x.x.x`, `/home/<user>/` → `~/`. Strips, never rejects (a learning with a hostname in it is still a learning). Hash computed from scrubbed content → PII-bearing retries still dedup. |
| L-3 | Deterministic dedup at write | UNIQUE (route, content_hash); `ON CONFLICT DO NOTHING` → capture() is idempotent, returns `{id, deduped, status}`. Monday semantic merge (near-dup by embedding) is a separate F-006+ pass. |
| L-4 | Status lifecycle + impact | pending → evaluated → applied → verified → retired (CHECK). impact_score -3..+3 (0=unknown, +improvement, -regression). |
| L-5 | Zero LLM cost on agent side | Collectors are no_agent scripts (`learning-collect.py`); the server inserts; no agent-side LLM. |
| L-6 | RLS fail-closed | RLS enabled; un-granted role sees zero rows (verified: temp worker role → permission denied). Lifecycle SELECT granted to orchestrator profile roles only. |

### Write path details

- **CLI** `ops/scripts/manage/learning-collect.py` (all agents): `--route`,
  `--content`/`--content-file`, `--type`, `--impact`, `--source-ref`,
  `--dry-run`, `--list-routes`. Watchdog semantics: exit 0 + empty stdout on
  success (incl. dedup), exit 1 + stderr on failure. Silent = healthy.
- **Lib** `ops/scripts/lib/cortex_bus.py::learning_capture()` — shared client,
  reuses `_bus_post` (Bearer→Basic 401 fallback, primary→fallback URL
  retry). Errors logged, never raised — a lost learning beats a crashed
  collector.
- **Server** `core/cortex_bus/server.py::POST /api/learnings` — authenticates
  via existing `_authenticate` (Bearer token or nginx X-Forwarded-User),
  validates route/type/impact against the canonical allowlists (clean 400s),
  calls `learnings.capture()` as the owner connection. Agent identity is
  **always** from auth, never the request body.

### Route enum (canonical 8)

`brain_pending` · `brain_lessons` · `session_corrections` · `governance_cycles`
· `llm_judge` · `remediation` · `user_feedback` · `cron_outputs`

Adding a route = v00X migration (deliberate — keeps F-015 protocol registry
honest). The server mirrors the enum for clean 400s; the DB CHECK is
fail-closed.

## Schema & migrations

- DDL: `ops/services/learnings/schema/v001__learnings.sql`
- Runner: `ops/services/learnings/migrate.py` — version-gated
  (`learnings.schema_version`), mirror of tasks/migrate.py, DDL as `mycortex`
  owner. Registered `register_orch` — **orchestrator-only**: the bus Postgres
  exists only on Moses/Esther. Workers write via HTTP and never need the
  schema locally.
- Applied by cortex-update.sh after file sync (same guarded pattern as tasks).

## Deployment

| Artifact | Deploy scope | Registered |
|----------|-------------|------------|
| learnings schema + migrate.py | orchestrators only | register_orch |
| learning-collect.py | all agents | register |
| server.py endpoint | runs from repo (bus service) | in-repo change |

Bus service restart needed after server.py changes: `systemctl --user restart
cortex-bus.service` (or launchd on macOS). Moses picks up the endpoint on his
next pull + restart; until then his :13004 returns 404 for /api/learnings
(workers already fail over to Esther via lib fallback).

## Testing

`tests/test-learnings-schema.sh` — hermetic scratch DB battery, 16 checks:
fresh apply, idempotent re-run, dedup (same id + 1 row), distinct-content
rows, scrub hook (all 3 patterns), INSERT-only (reader EXECUTE ok, table
INSERT permission-denied), set_status (transition + invalid rejected),
RLS fail-closed (temp worker role blocked; esther lifecycle reads), bus
schema untouched. Run: `bash tests/test-learnings-schema.sh`.

Live E2E (2026-08-08): POST /api/learnings via local Bearer → new id,
dedup → `{deduped:true}` same id, bad route → 400; CLI capture/dedup/
content-file all exit 0; external nginx :14004 + Basic → 200.

## Follow-ups (other tasks)

- **F-002** — remediation fixer writes ledger row on novel success
  (idempotent by fix signature)
- **F-006** — orch-skill-lifecycle consumes ledger, writes disposition +
  impact via set_status()
- **F-003/F-004** — user feedback + watchdog findings routes wired
- **F-007** — ledger→tasks promotion (idempotent by ledger_id)
- **F-020** — daily "what the fleet learned" digest
- **F-009** — skill hit-rate tracking
- Forwarder row-level mirror of learnings between Moses/Esther (schema exists
  on both; cross-host row sync is a later hardening)
