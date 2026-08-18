---
name: bus-archive-diagnostics
description: "Query bus queues and archives reliably for fleet results."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [bus, pgmq, archives, diagnostics, sql, fleet, verification]
    related_skills: [fleet-commands, cortex-bus, mcp-health-monitoring]
---

# Bus Archive Diagnostics

Reliable read-side queries against the Agent Bus PGMQ store — the patterns for
peeking queues, extracting result payloads, and verifying fleet command
outcomes without hitting the two silent traps that waste queries: the
double-encoded `body` column and raw-string rows that crash unguarded casts.

## When to Use

- Verifying UPDATE_REQUEST / EXEC / ROLLBACK_REQUEST results (UPDATE_RESULT /
  EXEC_RESULT) after a fleet dispatch
- Inspecting `bus.messages` / `bus.archives` via psql (docker exec into
  mycortex-postgres)
- Answering "did the fleet actually update / respond?"

## The Two Traps (both cost real queries on 2026-08-18)

1. **`body` is double-encoded.** The envelope object's `body` field is a JSON
   **string**, not an object. `->'body'` yields a jsonb string node — any
   `->>'field'` on it returns NULL silently. Correct extraction:
   `((body::jsonb #>> '{}')::jsonb->>'body')::jsonb->>'success'`
   (unwrap to text with `->>'body'`, then `::jsonb` parses, then read fields).
2. **Raw-string rows crash unguarded casts.** Archives contain rows whose
   `body` is a bare string (e.g. a literal `PING`). The double-parse
   `(body::jsonb #>> '{}')::jsonb` on such a row throws
   `invalid input syntax for type json: Token "PING"` and kills the whole
   query. **Always put `jsonb_typeof(body::jsonb)='object'` as the FIRST WHERE
   clause** — AND short-circuits left-to-right per row, so the guard prevents
   the cast from ever evaluating on non-object rows.

## Canonical Queries

```sql
-- UPDATE_RESULTs from the last N minutes (correct inner-body extraction):
SELECT archived_at::timestamptz(0),
       (body::jsonb #>> '{}')::jsonb->>'correlation_id',
       COALESCE(((body::jsonb #>> '{}')::jsonb->>'body')::jsonb->>'success',''),
       COALESCE(((body::jsonb #>> '{}')::jsonb->>'body')::jsonb->>'git_sha_after','')
FROM bus.archives
WHERE jsonb_typeof(body::jsonb)='object'          -- guard FIRST
  AND (body::jsonb #>> '{}')::jsonb->>'subject'='UPDATE_RESULT'
  AND archived_at > NOW() - INTERVAL '30 minutes'
ORDER BY archived_at;

-- Live queue state for a correlation batch:
SELECT queue_name, state,
       (body::jsonb #>> '{}')::jsonb->>'correlation_id'
FROM bus.messages
WHERE jsonb_typeof(body::jsonb)='object'
  AND (body::jsonb #>> '{}')::jsonb->>'correlation_id' LIKE 'fleet-notify-%'
ORDER BY queue_name;
```

## Verify with the Live Bus, Not the Local Mirror

psql via `docker exec` on your own host may hit the **local mycortex-postgres
(15432), which is a REPORTS MIRROR, never authoritative** — queue state there
can be stale or empty while the live bus (CORTEX_BUS_URL, e.g.
https://host:13004) has the real messages. The `hc` CLI routes over HTTP to
the ACTIVE bus — use `hc inbox <agent>` (peek), `hc status`, `hc bus --all`
for authoritative reads. (Archives do replicate to the mirror, so archive
queries via psql are generally trustworthy.)

## Missing Results ≠ Missing Update

Fleet handlers early-archive the request before processing, so a consumed
UPDATE_REQUEST proves only that it was READ — never that the update ran or
that a result was sent. The UPDATE_RESULT response path has failed silently on
fleet hosts while the updates themselves landed (2026-08-18: 5/5 requests
consumed, 0/5 results, joseph fully updated at the target SHA). **Ground
truth when results are missing:** `hc exec <agent> cortex-doctor.py --quiet`
(greps: `Repo sync`, `Deploy sync`, `Checksum: <changed file>`) — the EXEC
round-trip uses a different code path and often works when the UPDATE result
send failed. `Deploy sync: deployed commit matches HEAD` + a passing checksum
for the shipped file = the update landed, response lost.

## Pitfalls

- `hc exec` polls ~5 min and can time out right before a result lands — for
  slow agents, prefer `hc send <agent> EXEC '<json>' --self-tested` then poll
  archives after ~5.5 min (decoupled pattern).
- EXEC_RESULT `success: false` with a doctor dump that shows only ✅ lines =
  the doctor exited non-zero on WARNINGS (Overall: WARNING), not a failed run.
- A doctor `exit=1` with empty stderr from a fleet update is the known
  "soft success" (needs_update() returns 1 for unchanged files) — check
  `git_sha_after == target_sha`, not the exit code.
- Always check BOTH `bus.messages` (live) and `bus.archives` — results are
  consumed+archived by the orchestrator's own handler within minutes.
